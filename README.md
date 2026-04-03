# OpenBlend

> Cross-platform shared playlist engine for Spotify and Apple Music users.

One person on Spotify, one on Apple Music. OpenBlend connects both accounts, analyzes their listening history, finds common ground, and builds a shared playlist that works on both platforms — updated automatically on a schedule.

---

## The Problem

Spotify has a "Blend" feature that creates shared playlists between two users — but only if both are on Spotify. There is no native cross-platform equivalent. If your friend is on Apple Music and you are on Spotify, you have no way to discover music together.

---

## How It Works

OpenBlend runs a pipeline on a schedule (or manually on demand):

1. **Ingest** — pulls listening data from both accounts: top tracks, saved songs, playlist contents, recently played.

2. **Normalize** — strips platform-specific noise (`feat.`, `Remastered`, `Radio Edit`, etc.) and maps every track to a unified internal representation using ISRC where available, fuzzy matching otherwise.

3. **Score** — builds a taste profile per user based on how strongly each track signals their preference (source type, recency, repeat exposure).

4. **Candidate pool** — assembles tracks in three categories:
   - tracks both users already like
   - tracks the Spotify user loves but the Apple Music user hasn't heard
   - tracks the Apple Music user loves but the Spotify user hasn't heard

5. **LLM ranking** — an AI model selects the best ~40 tracks from the pool, assigns each to a bucket, and writes a short explanation for why it fits both users. The model never suggests tracks outside the pre-built pool — no hallucination risk.

6. **Validate** — every selected track is looked up on both platforms. Only tracks confirmed to exist on both make the final playlist. A repair loop runs if there aren't enough valid results.

7. **Publish** — the final playlist is pushed to a target playlist on Spotify and a target playlist on Apple Music, interleaved across buckets for a natural listening flow.

---

## Stack

FastAPI · Angular · PostgreSQL · Docker Compose · OpenAI GPT

---