"""Windows executable entrypoint; no service starts without explicit CLI consent."""
if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    import os,sys
    try:
        if len(sys.argv)>1 and sys.argv[1] in ('bridge','reader-diagnose','virtual-reader'):
            from nexvary_usim_lab.__main__ import main as cli
            raise SystemExit(cli())
        from nexvary_usim_lab.gui import main
        main()
    except Exception:
        # Only disposable CI smoke collects a traceback; no hardware/secrets used.
        marker=os.environ.get('NEXVARY_PACKAGE_SMOKE')
        if marker:
            import traceback
            from pathlib import Path
            Path(marker+'.error').write_text(traceback.format_exc(),encoding='utf-8')
        raise
