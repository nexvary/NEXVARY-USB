// Local development trust only. No boot/security-policy changes.
#include <windows.h>
#include <wincrypt.h>
#include <shellapi.h>
#include <shlobj.h>
#include <string>
#include <vector>
#include <stdexcept>
#include "local_certificate_pin.h"
static void check(bool ok,const char* what){if(!ok)throw std::runtime_error(std::string(what)+": "+std::to_string(GetLastError()));}
struct File {HANDLE h=INVALID_HANDLE_VALUE;~File(){if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);}};
static std::vector<BYTE> bytes(File& f,const std::wstring& path){
    f.h=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,0,nullptr);check(f.h!=INVALID_HANDLE_VALUE,"Open pinned package member");
    LARGE_INTEGER size;check(GetFileSizeEx(f.h,&size)!=FALSE && size.QuadPart>0 && size.QuadPart<8*1024*1024,"Bound package size");
    std::vector<BYTE> b(static_cast<size_t>(size.QuadPart));DWORD got=0;check(ReadFile(f.h,b.data(),static_cast<DWORD>(b.size()),&got,nullptr)!=FALSE && got==b.size(),"Read package");return b;
}
static std::wstring hex(const BYTE* b,DWORD n){std::wstring s;for(DWORD i=0;i<n;++i){s+=L"0123456789ABCDEF"[b[i]>>4];s+=L"0123456789ABCDEF"[b[i]&15];}return s;}
static DWORD run(const std::wstring& exe,const std::wstring& args,HANDLE report){
    STARTUPINFOW si={};si.cb=sizeof(si);if(report!=INVALID_HANDLE_VALUE){si.dwFlags=STARTF_USESTDHANDLES;si.hStdOutput=report;si.hStdError=report;si.hStdInput=GetStdHandle(STD_INPUT_HANDLE);}
    PROCESS_INFORMATION pi={};std::wstring command=L"\""+exe+L"\" "+args;
    check(CreateProcessW(exe.c_str(),command.data(),nullptr,nullptr,report!=INVALID_HANDLE_VALUE,CREATE_NO_WINDOW,nullptr,nullptr,&si,&pi)!=FALSE,"Launch package validation");
    CloseHandle(pi.hThread);DWORD wait=WaitForSingleObject(pi.hProcess,120000);DWORD code=1;
    if(wait==WAIT_OBJECT_0)GetExitCodeProcess(pi.hProcess,&code);
    else {TerminateProcess(pi.hProcess,1);WaitForSingleObject(pi.hProcess,5000);}
    CloseHandle(pi.hProcess);check(wait==WAIT_OBJECT_0,"Installer timeout");return code;
}
int WINAPI wWinMain(HINSTANCE,HINSTANCE,PWSTR,int){
    PCCERT_CONTEXT cert=nullptr;HCERTSTORE stores[2]={};bool added[2]={};
    auto close=[&](bool rollback){for(int i=0;i<2;++i)if(stores[i]){if(rollback && added[i] && cert){PCCERT_CONTEXT found=CertFindCertificateInStore(stores[i],X509_ASN_ENCODING,0,CERT_FIND_EXISTING,cert,nullptr);if(found)CertDeleteCertificateFromStore(found);}CertCloseStore(stores[i],0);stores[i]=nullptr;}if(cert){CertFreeCertificateContext(cert);cert=nullptr;}};
    try {
        wchar_t own[32768]={};DWORD length=GetModuleFileNameW(nullptr,own,32768);check(length>0 && length<32768,"Executable path");
        if(!IsUserAnAdmin()){SHELLEXECUTEINFOW e={};e.cbSize=sizeof(e);e.fMask=SEE_MASK_NOCLOSEPROCESS;e.lpVerb=L"runas";e.lpFile=own;e.nShow=SW_SHOWNORMAL;check(ShellExecuteExW(&e)!=FALSE,"Administrator approval");if(e.hProcess)CloseHandle(e.hProcess);return 0;}
        std::wstring base(own,length);base=base.substr(0,base.find_last_of(L"\\/"));
        File locked[5];std::vector<BYTE> certificate;
        for(int i=0;i<5;++i){auto b=bytes(locked[i],base+L"\\"+PinnedFiles[i]);BYTE hash[32];DWORD size=32;check(CryptHashCertificate2(L"SHA256",0,nullptr,b.data(),static_cast<DWORD>(b.size()),hash,&size)!=FALSE && hex(hash,size)==PinnedHashes[i],"Package SHA256 mismatch");if(i==4)certificate=b;}
        cert=CertCreateCertificateContext(X509_ASN_ENCODING,certificate.data(),static_cast<DWORD>(certificate.size()));check(cert!=nullptr,"Public certificate");
        check(CertVerifyTimeValidity(nullptr,cert->pCertInfo)==0,"Certificate expiry");
        std::wstring message=L"هذه حزمة تطوير محلية، وليست شهادة عامة أو اعتماد Microsoft.\nسيُضاف مفتاحها العام إلى Root وTrustedPublisher على هذا الكمبيوتر.\nلن تتغير إعدادات Secure Boot أو حماية التعريفات.\n\nبصمة SHA256 للشهادة:\n"+std::wstring(PinnedHashes[4])+L"\n\nهل تريد تجربة التثبيت؟";
        if(MessageBoxW(nullptr,message.c_str(),L"NEXVARY — موافقة الثقة المحلية",MB_YESNO|MB_ICONWARNING|MB_DEFBUTTON2|MB_RIGHT|MB_RTLREADING)!=IDYES){close(false);return 0;}
        for(int i=0;i<2;++i){stores[i]=CertOpenStore(CERT_STORE_PROV_SYSTEM_W,0,0,CERT_SYSTEM_STORE_LOCAL_MACHINE,i==0?L"Root":L"TrustedPublisher");check(stores[i]!=nullptr,"Open local trust store");PCCERT_CONTEXT found=CertFindCertificateInStore(stores[i],X509_ASN_ENCODING,0,CERT_FIND_EXISTING,cert,nullptr);if(found)CertFreeCertificateContext(found);else{check(CertAddCertificateContextToStore(stores[i],cert,CERT_STORE_ADD_NEW,nullptr)!=FALSE,"Add pinned public certificate");added[i]=true;}}
        wchar_t desktop[MAX_PATH]={};check(SUCCEEDED(SHGetFolderPathW(nullptr,CSIDL_DESKTOPDIRECTORY,nullptr,SHGFP_TYPE_CURRENT,desktop)),"Desktop report path");
        SECURITY_ATTRIBUTES attr={sizeof(attr),nullptr,TRUE};File report;std::wstring log=std::wstring(desktop)+L"\\NEXVARY-Local-Reader-Install.log";
        report.h=CreateFileW(log.c_str(),GENERIC_WRITE,FILE_SHARE_READ,&attr,CREATE_ALWAYS,0,nullptr);check(report.h!=INVALID_HANDLE_VALUE,"Create install report");
        DWORD code=run(base+L"\\NEXVARY-Reader-Setup.exe",L"--install",report.h);
        if(code){close(true);MessageBoxW(nullptr,(L"لم ينجح التثبيت. أُزيلت الثقة التي أضافتها هذه المحاولة فقط.\nرمز النتيجة: "+std::to_wstring(code)+L"\nالتقرير: "+log).c_str(),L"NEXVARY",MB_OK|MB_ICONERROR|MB_RIGHT|MB_RTLREADING);return static_cast<int>(code);}
        close(false);
        run(base+L"\\NEXVARY-Reader-Setup.exe",L"",INVALID_HANDLE_VALUE);
        return 0;
    }catch(const std::exception& e){close(true);std::string error=e.what();std::wstring wide(error.begin(),error.end());MessageBoxW(nullptr,wide.c_str(),L"NEXVARY — لم تكتمل التجربة",MB_OK|MB_ICONERROR);return 1;}
}
