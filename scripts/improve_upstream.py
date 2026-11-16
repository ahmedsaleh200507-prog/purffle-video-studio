"""Verify and smoke-test the pinned runtime adapter, without editing upstream files."""
from studio_runtime import install, verify_upstream


def main():
    revision = verify_upstream()
    install()
    print(f"Audited upstream {revision}; strict moving-video runtime adapter ready", flush=True)


if __name__ == "__main__":
    main()
