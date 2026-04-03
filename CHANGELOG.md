# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Phase 1: Foundation — Docker Compose, FastAPI skeleton, PostgreSQL models, Alembic migrations
- Spotify OAuth2 PKCE authentication flow
- Apple Music authentication (MusicKit JS + developer token)
- User provisioning from `users_config.json` on first startup
- First-login forced password change flow
- Forgot-password reset log file mechanism
- Angular 21 frontend with login and change-password pages
- JWT-based authentication (access token)
