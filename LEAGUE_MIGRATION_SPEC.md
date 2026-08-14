# League Migration Spec

## Purpose

After season 10, the league changed from 6 players / 3 teams to 9 players / 3 teams.
The existing 6 players continue, and 3 new players join.
The same Mahjong Soul tournament/contest named `テスト` is reused for the new league.

The site should preserve the old league results, start the new league from zero, and also provide combined totals.
From the new league onward, personal data must exist in two forms:

- new-league-only personal stats
- combined lifetime personal stats

## Data Eras

Use an era field when possible.

- `old`: current 6-player league, seasons 1 to 10
- `new`: 9-player league, starting after season 10
- `combined`: derived view that aggregates `old` + `new`

Season 10 completion is the cutoff point.
Season 11 and later belong to `new` unless explicitly overridden.

## Page Structure

The published HTML should have these top-level views.

- `新リーグ`: new 9-player league only, reset from zero
- `通算`: old league + new league combined
- `旧リーグ`: seasons 1 to 10 only
- individual season tabs

Recommended tab order after migration:

- `新リーグ`
- latest new-league season
- older new-league seasons
- `通算`
- `旧リーグ`
- old season tabs, if still displayed

The exact tab order can be adjusted at implementation time, but the user-facing distinction between old, new, and combined must remain clear.

## Old League Preservation

Season 10 is the final old-league season. Freeze the old result files so old results do not change accidentally.

Recommended archive layout:

- `data/old/`
  - old season paifu CSVs, seasons 1 to 10
  - old `summary.csv`
  - old `yakuman_summary.csv`
  - old `yakuman_details.csv`
  - old team data

The old archive should be treated as read-only source data after migration.

## New League Collection

New league results should be collected into separate files.
Do not append new-league season IDs directly into the old-league source files.

Recommended layout:

- `data/new/`
  - new season paifu CSVs
  - new raw records
  - new team data

New league cumulative stats start from zero. New members should have no old-era stats, but they should appear in combined pages with their new-era totals.

The new league uses 9 players / 3 teams, with 3 players per team.
Team data must therefore support 3 members per team without assuming the old 2-player team shape.

## Combined View / Lifetime View

The combined page aggregates old + new data.
The user-facing label should be `通算`.

Include the same major sections as the current cumulative page:

- digest
- ranking / placement stats
- win and deal-in stats
- riichi quality
- call quality
- deal-in quality
- yakuman victim ranking
- yakuman winner ranking
- yakuman details
- player pages

For players who only exist in the new league, old-era values are zero or blank as appropriate.

For the original 6 players, combined personal pages must show lifetime totals across both eras.
For the 3 new players, combined personal pages are the same as their new-league totals until they accumulate multiple eras.

## Team Handling

Teams can change by season.

Team stats must always be season-aware. Do not assume a player has one fixed team across eras.

For old/new/combined views:

- old team results use old season team assignments
- new team results use new season team assignments
- combined personal pages can include team championship counts across both eras

The same contest name `テスト` does not identify the era. Era must be derived from season number or explicit data location.

## Important Note

The old and new leagues are not perfectly identical conditions because the player pool changes from 6 to 9 players.

The combined page is useful as a lifetime total, but comparisons between old league and new league should be displayed separately as well.
Primary current-performance pages should use the new-league-only stats.

## Implementation Notes

Expected future code changes:

- add an era/cutoff layer to aggregation
- make `make_site.py` read old and new data sources separately
- generate new/old/lifetime tabs
- keep current season tabs working
- ensure new members appear correctly in new and combined views
- ensure old-only players, if any appear later, remain visible in old and combined views
- update manual AI comments so they can differ between new-league-only and lifetime personal pages
