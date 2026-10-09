"""Windows executable entrypoint; no network service is launched."""
from nexvary_usim_lab.gui import main

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    import sys
    if len(sys.argv)>1 and sys.argv[1]=="bridge":
        from nexvary_usim_lab.__main__ import main as cli
        raise SystemExit(cli())
    main()
