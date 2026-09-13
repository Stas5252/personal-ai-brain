# Reproducible build policy

Production inputs are immutable or exact:

- Python base image: exact patch tag plus OCI index digest in `Dockerfile`.
- Open WebUI: exact release tag plus image digest in `docker-compose.yml`.
- Python environment: every direct and transitive package is exact in `requirements.lock`; CI and image build install it with `--no-deps` and run `pip check`.
- GitHub Actions: verified current majors are pinned to full commit SHA with the release tag kept in a comment.
- CI executes Python 3.12, the complete non-live test suite, Compose validation, image build and startup smoke.

## Controlled refresh

1. Create a dedicated dependency PR.
2. Resolve `requirements.txt` in a clean Python 3.12 environment.
3. Run `pip freeze --exclude-editable | sort` and replace `requirements.lock` completely; do not hand-update only top-level packages.
4. Install with `pip install --no-deps -r requirements.lock`, run `pip check`, full offline tests, image build and startup smoke.
5. For Actions, verify the upstream release and resolve its tag to a full commit SHA. Upgrade a major only when its runtime is supported by GitHub-hosted runners; do not silence runtime deprecation warnings.
6. For images, resolve the multi-platform OCI index digest from the authoritative registry/repo-info and keep the human-readable patch tag before `@sha256:`.
7. Record the green CI run and image digest in the release checklist.

Do not use floating Action majors, `latest` image tags, unbounded Python ranges for installation, or an unpinned `pip install --upgrade pip` in production builds.
