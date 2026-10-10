// NEXVARY dedicated root reader setup. No certificate or security-policy changes.
#include <windows.h>
#include <setupapi.h>
#include <newdev.h>
#include <winscard.h>
#include <wintrust.h>
#include <softpub.h>
#include <mscat.h>
#include <shlobj.h>
#include <string>
#include <vector>
#include <iostream>
#include <stdexcept>
#include <cwctype>

static const GUID ReaderClass = {0x50dd5230,0xba8a,0x11d1,{0xbf,0x5d,0,0,0xf8,5,0xf5,0x30}};
static const wchar_t HardwareId[] = L"root\\NEXVARYVirtualSIMReader";
struct Handle {
    HANDLE value=INVALID_HANDLE_VALUE;
    ~Handle(){if(value!=INVALID_HANDLE_VALUE) CloseHandle(value);}
};
struct Devices {
    HDEVINFO value=INVALID_HANDLE_VALUE;
    ~Devices(){if(value!=INVALID_HANDLE_VALUE) SetupDiDestroyDeviceInfoList(value);}
};
static void require(bool ok,const char* operation){if(!ok) throw std::runtime_error(std::string(operation)+": "+std::to_string(GetLastError()));}
static std::wstring ownDirectory(){
    std::vector<wchar_t> path(32768);
    DWORD size=GetModuleFileNameW(nullptr,path.data(),static_cast<DWORD>(path.size()));
    require(size>0 && size<path.size(),"Executable path");
    std::wstring result(path.data(),size);return result.substr(0,result.find_last_of(L"\\/"));
}
static LONG verifyFile(const std::wstring& path){
    WINTRUST_FILE_INFO info={};info.cbStruct=sizeof(info);info.pcwszFilePath=path.c_str();
    WINTRUST_DATA trust={};trust.cbStruct=sizeof(trust);trust.dwUIChoice=WTD_UI_NONE;
    trust.fdwRevocationChecks=WTD_REVOKE_WHOLECHAIN;trust.dwProvFlags=WTD_REVOCATION_CHECK_CHAIN_EXCLUDE_ROOT;
    trust.dwUnionChoice=WTD_CHOICE_FILE;trust.pFile=&info;trust.dwStateAction=WTD_STATEACTION_VERIFY;
    GUID action=WINTRUST_ACTION_GENERIC_VERIFY_V2;
    LONG result=WinVerifyTrust(nullptr,&action,&trust);
    trust.dwStateAction=WTD_STATEACTION_CLOSE;WinVerifyTrust(nullptr,&action,&trust);return result;
}
static LONG verifyMember(HCATADMIN admin,HANDLE file,const std::wstring& path,const std::wstring& catalog){
    // Resolve SHA256 APIs dynamically as documented by Microsoft.
    HMODULE wintrust=GetModuleHandleW(L"wintrust.dll");
    auto hashFn=reinterpret_cast<decltype(&CryptCATAdminCalcHashFromFileHandle2)>(GetProcAddress(wintrust,"CryptCATAdminCalcHashFromFileHandle2"));
    if(!hashFn)return TRUST_E_PROVIDER_UNKNOWN;
    DWORD size=0;if(!hashFn(admin,file,&size,nullptr,0) || !size || size>128)return TRUST_E_BAD_DIGEST;
    std::vector<BYTE> hash(size);if(!hashFn(admin,file,&size,hash.data(),0))return TRUST_E_BAD_DIGEST;
    std::wstring tag;const wchar_t* hex=L"0123456789ABCDEF";
    for(DWORD i=0;i<size;++i){tag+=hex[hash[i]>>4];tag+=hex[hash[i]&15];}
    WINTRUST_CATALOG_INFO info={};info.cbStruct=sizeof(info);info.pcwszCatalogFilePath=catalog.c_str();
    info.pcwszMemberTag=tag.c_str();info.pcwszMemberFilePath=path.c_str();info.hMemberFile=file;
    info.pbCalculatedFileHash=hash.data();info.cbCalculatedFileHash=size;info.hCatAdmin=admin;
    WINTRUST_DATA trust={};trust.cbStruct=sizeof(trust);trust.dwUIChoice=WTD_UI_NONE;
    trust.fdwRevocationChecks=WTD_REVOKE_WHOLECHAIN;trust.dwProvFlags=WTD_REVOCATION_CHECK_CHAIN_EXCLUDE_ROOT;
    trust.dwUnionChoice=WTD_CHOICE_CATALOG;trust.pCatalog=&info;trust.dwStateAction=WTD_STATEACTION_VERIFY;
    GUID action=WINTRUST_ACTION_GENERIC_VERIFY_V2;LONG result=WinVerifyTrust(nullptr,&action,&trust);
    trust.dwStateAction=WTD_STATEACTION_CLOSE;WinVerifyTrust(nullptr,&action,&trust);return result;
}
struct Package {
    std::wstring base=ownDirectory(),inf=base+L"\\NEXVARYVirtualSIMReader.inf",dll=base+L"\\NEXVARYVirtualSIMReader.dll",cat=base+L"\\nexvaryvirtualsimreader.cat";
    Handle infFile,dllFile,catFile;
    LONG signature=TRUST_E_NOSIGNATURE,infTrust=TRUST_E_NOSIGNATURE,dllTrust=TRUST_E_NOSIGNATURE;
    bool complete=false,identity=false;
    Package(){
        infFile.value=CreateFileW(inf.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,0,nullptr);
        dllFile.value=CreateFileW(dll.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,0,nullptr);
        catFile.value=CreateFileW(cat.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,0,nullptr);
        complete=infFile.value!=INVALID_HANDLE_VALUE && dllFile.value!=INVALID_HANDLE_VALUE && catFile.value!=INVALID_HANDLE_VALUE;
        if(!complete)return;
        HINF parsed=SetupOpenInfFileW(inf.c_str(),nullptr,INF_STYLE_WIN4,nullptr);
        if(parsed!=INVALID_HANDLE_VALUE){
            INFCONTEXT line={};wchar_t id[256]={};wchar_t classId[128]={};wchar_t binary[256]={};
            identity=SetupFindFirstLineW(parsed,L"Standard.NTamd64",nullptr,&line) && SetupGetStringFieldW(&line,2,id,256,nullptr) && _wcsicmp(id,HardwareId)==0;
            identity=identity && SetupFindFirstLineW(parsed,L"Version",L"ClassGuid",&line) && SetupGetStringFieldW(&line,1,classId,128,nullptr) && _wcsicmp(classId,L"{50dd5230-ba8a-11d1-bf5d-0000f805f530}")==0;
            identity=identity && SetupFindFirstLineW(parsed,L"NEXVARYVirtualSIMReader_Install",L"ServiceBinary",&line) && SetupGetStringFieldW(&line,1,binary,256,nullptr) && _wcsicmp(binary,L"%12%\\UMDF\\NEXVARYVirtualSIMReader.dll")==0;
            SetupCloseInfFile(parsed);
        }
        signature=verifyFile(cat);if(signature!=ERROR_SUCCESS)return;
        auto acquire=reinterpret_cast<decltype(&CryptCATAdminAcquireContext2)>(GetProcAddress(GetModuleHandleW(L"wintrust.dll"),"CryptCATAdminAcquireContext2"));
        HCATADMIN admin=nullptr;
        if(acquire && acquire(&admin,nullptr,L"SHA256",nullptr,0)){
            infTrust=verifyMember(admin,infFile.value,inf,cat);dllTrust=verifyMember(admin,dllFile.value,dll,cat);
            CryptCATAdminReleaseContext(admin,0);
        }
    }
    bool trusted()const{return complete && identity && signature==0 && infTrust==0 && dllTrust==0;}
};
static unsigned ownDevices(){
    Devices list;list.value=SetupDiGetClassDevsW(&ReaderClass,nullptr,nullptr,0);require(list.value!=INVALID_HANDLE_VALUE,"Enumerate root readers");
    unsigned count=0;SP_DEVINFO_DATA data={};data.cbSize=sizeof(data);
    for(DWORD i=0;SetupDiEnumDeviceInfo(list.value,i,&data);++i){
        wchar_t instance[512]={};require(SetupDiGetDeviceInstanceIdW(list.value,&data,instance,512,nullptr)!=FALSE,"Device instance");
        std::wstring id(instance);if(id.size()<29 || _wcsnicmp(id.c_str(),L"ROOT\\NEXVARYVIRTUALSIMREADER\\",29)!=0)continue;
        wchar_t ids[4096]={};DWORD type=0;
        require(SetupDiGetDeviceRegistryPropertyW(list.value,&data,SPDRP_HARDWAREID,&type,reinterpret_cast<BYTE*>(ids),sizeof(ids),nullptr)!=FALSE,"Hardware identity");
        require(type==REG_MULTI_SZ,"Hardware property type");
        for(const wchar_t* p=ids;*p;p+=wcslen(p)+1)if(_wcsicmp(p,HardwareId)==0){++count;break;}
    }
    require(GetLastError()==ERROR_NO_MORE_ITEMS,"Finish enumeration");return count;
}
static bool pcscStatus(){
    SCARDCONTEXT context=0;LONG status=SCardEstablishContext(SCARD_SCOPE_USER,nullptr,nullptr,&context);
    bool found=false;DWORD readers=0;
    if(status==SCARD_S_SUCCESS){
        DWORD size=0;status=SCardListReadersW(context,nullptr,nullptr,&size);
        if(status==SCARD_S_SUCCESS && size>1 && size<65536){
            std::vector<wchar_t> names(size);status=SCardListReadersW(context,nullptr,names.data(),&size);
            if(status==SCARD_S_SUCCESS)for(const wchar_t* n=names.data();*n;n+=wcslen(n)+1){++readers;std::wstring name(n);for(auto& c:name)c=static_cast<wchar_t>(towupper(c));if(name.find(L"NEXVARY")!=std::wstring::npos)found=true;}
        }
        SCardReleaseContext(context);
    }
    std::cout<<",\"pcsc_status\":"<<static_cast<unsigned long>(status)<<",\"pcsc_readers\":"<<readers<<",\"nexvary_reader_enumerated\":"<<(found?"true":"false")<<",\"card_connected\":false,\"apdu_tested\":false";
    return found;
}
static int inspect(Package& p,bool dialog=false){
    unsigned devices=ownDevices();
    std::cout<<"{\"schema\":\"nexvary.reader-setup.v1\",\"package_complete\":"<<(p.complete?"true":"false")<<",\"inf_identity_valid\":"<<(p.identity?"true":"false")<<",\"trusted_package\":"<<(p.trusted()?"true":"false")<<",\"catalog_trust_status\":"<<static_cast<unsigned long>(p.signature)<<",\"inf_trust_status\":"<<static_cast<unsigned long>(p.infTrust)<<",\"dll_trust_status\":"<<static_cast<unsigned long>(p.dllTrust)<<",\"own_root_devices\":"<<devices;
    bool enumerated=pcscStatus();std::cout<<"}\n";
    if(dialog){
        std::wstring message=L"توقيع الحزمة وسلامتها: ";
        message+=p.trusted()?L"اجتازت الفحص":L"غير جاهزة للتثبيت";
        message+=L"\nأجهزة NEXVARY المسجلة: "+std::to_wstring(devices);
        message+=enumerated?L"\nتعداد PC/SC: ظهر قارئ NEXVARY":L"\nتعداد PC/SC: لم يثبت ظهور قارئ NEXVARY";
        message+=L"\n\nالفحص لا يثبت الاتصال بالشريحة أو نقل APDU.\n";
        if(!p.trusted())message+=L"الحزمة الحالية غير موقعة أو لم تجتز التحقق. لم يتم إنشاء جهاز أو تغيير إعدادات Windows. يلزم توقيع موثوق قبل التثبيت.";
        else message+=L"لتثبيت حزمة موقعة: شغّل Install-Reader.cmd بصلاحية المسؤول. ثم افحص تعداد القارئ والاتصال داخل USB Studio.";
        MessageBoxW(nullptr,message.c_str(),L"NEXVARY — فحص تعريف القارئ",MB_OK|MB_ICONINFORMATION|MB_RIGHT|MB_RTLREADING);
    }
    return 0;
}
static int install(Package& p){
    // All authentication and integrity gates precede device creation or driver-store writes.
    if(!p.trusted()){std::cerr<<"BLOCKED: package is missing, mismatched, unsigned, untrusted or changed. No device created.\n";return 20;}
    if(!IsUserAnAdmin()){std::cerr<<"Administrator elevation required.\n";return 21;}
    unsigned count=ownDevices();if(count>1){std::cerr<<"Multiple NEXVARY root devices; inspect before installation.\n";return 22;}
    if(count==1){std::cout<<"Existing NEXVARY device preserved; no duplicate or forced driver update.\n";return inspect(p);}
    Devices list;list.value=SetupDiCreateDeviceInfoList(&ReaderClass,nullptr);require(list.value!=INVALID_HANDLE_VALUE,"Create device list");
    SP_DEVINFO_DATA data={};data.cbSize=sizeof(data);
    require(SetupDiCreateDeviceInfoW(list.value,L"NEXVARYVirtualSIMReader",&ReaderClass,L"NEXVARY Virtual SIM Reader",nullptr,DICD_GENERATE_ID,&data)!=FALSE,"Create root device information");
    // Literal contains the additional MULTI_SZ terminating null.
    wchar_t hardware[]=L"root\\NEXVARYVirtualSIMReader\0";
    require(SetupDiSetDeviceRegistryPropertyW(list.value,&data,SPDRP_HARDWAREID,reinterpret_cast<BYTE*>(hardware),sizeof(hardware))!=FALSE,"Set hardware ID");
    require(SetupDiCallClassInstaller(DIF_REGISTERDEVICE,list.value,&data)!=FALSE,"Register root device");
    BOOL reboot=FALSE;
    if(!UpdateDriverForPlugAndPlayDevicesW(nullptr,HardwareId,p.inf.c_str(),0,&reboot)){
        DWORD error=GetLastError();SP_REMOVEDEVICE_PARAMS remove={};remove.ClassInstallHeader.cbSize=sizeof(SP_CLASSINSTALL_HEADER);remove.ClassInstallHeader.InstallFunction=DIF_REMOVE;remove.Scope=DI_REMOVEDEVICE_GLOBAL;
        BOOL rolledBack=SetupDiSetClassInstallParamsW(list.value,&data,&remove.ClassInstallHeader,sizeof(remove)) && SetupDiCallClassInstaller(DIF_REMOVE,list.value,&data);
        std::cerr<<"Install failed: "<<error<<"; newly created device rollback="<<rolledBack<<". Existing devices were not removed.\n";return 23;
    }
    std::cout<<"Driver installation API completed; reboot_required="<<reboot<<". Enumeration and APDU remain separate checks.\n";
    return inspect(p);
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc>2 || (argc==2 && wcscmp(argv[1],L"--check")!=0 && wcscmp(argv[1],L"--install")!=0)){std::cerr<<"Usage: NEXVARY-Reader-Setup.exe --check | --install\n";return 2;}
        Package p;if(argc==2 && wcscmp(argv[1],L"--install")==0)return install(p);return inspect(p,argc==1);
    }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 30;}
}
