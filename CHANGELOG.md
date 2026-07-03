# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Professional open-source repository structure.
- Validated runtime settings and production configuration examples.
- Security headers, request IDs, rate limiting, and structured logging.
- Docker, Docker Compose, CI, and release workflow scaffolding.
- Water outage parser and endpoint for Novoyavorivskvodokanal Telegram posts.

### Changed

- Runtime data is written under a configurable data directory.
- API routes now include request validation metadata and OpenAPI tags.

## [1.0.0] - 2026-07-04

### Added

- Initial release-ready backend for electricity and water outage status.
- Naftogaz schedule parsing from Telegram text and OCR images.
- Lvivoblenergo address lookup and cache status endpoints.
- Android-friendly bootstrap and personal status endpoints.
