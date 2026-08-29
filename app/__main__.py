import sys

if "--argos-worker" in sys.argv:
    from app.argos_worker import main

    raise SystemExit(main())

from app.main import EstiloKaioApp


def main():
    app = EstiloKaioApp()
    app.mainloop()


if __name__ == "__main__":
    main()
