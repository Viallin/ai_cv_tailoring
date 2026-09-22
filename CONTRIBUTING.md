# Contributing

Thanks for your interest in AI CV Tailoring Builder. This started as a
personal project and is now open source — bug reports, feature ideas,
and PRs are all welcome, though as a single maintainer I can't promise a
fast turnaround.

## Getting set up

Follow the Quick start / Getting started sections in the
[README](README.md) to get the backend and frontend running locally.

## Running the tests

Backend:
```bash
uv run pytest
```

Frontend:
```bash
cd frontend
npm run test
npm run lint
```

Please make sure both pass before opening a PR.

## Making changes

- Keep PRs focused — one change per PR is easier to review than a bundle
  of unrelated fixes.
- Match the existing code style in the file you're editing. There's no
  enforced linter on the backend yet; the frontend uses oxlint
  (`npm run lint`).
- Add or update tests for the behavior you're changing.
- For anything nontrivial, opening an issue first to discuss the
  approach saves rework.

## License

By contributing, you agree that your contributions will be licensed
under this project's [GPL-3.0-or-later license](LICENSE).
