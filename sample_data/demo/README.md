# Stakeholder demo dataset (AusStage + DAAO)

33 hand-curated Linked Art records used by the local demo. They are seeded with:

```bash
.venv/bin/python scripts/seed_demo.py --data-dir demo_data
```

The seed script validates every record first (nothing is published if one is invalid), publishes places
first, and is safe to re-run: unchanged records are idempotent no-ops (no new versions).

| Partner  | File prefix        | Count | Linked Art type   |
|----------|--------------------|-------|-------------------|
| AusStage | `ausstage_venue_`  | 6     | `Place` (WKT `POINT(lon lat)` in `defined_by`) |
| AusStage | `ausstage_event_`  | 8     | `Activity` (`timespan`, `took_place_at` with inline coordinates, `carried_out_by`) |
| AusStage | `ausstage_person_` | 7     | `Person` (`born`, `carried_out` → events) |
| DAAO     | `daao_artist_`     | 6     | `Person` (`born`/`died` places, `carried_out[Production].produced` → works) |
| DAAO     | `daao_work_`       | 6     | `HumanMadeObject` (`produced_by`, `made_of`, `dimension`, `current_location`) |

Links run both ways: event ↔ person by IRI, event → venue (with the venue's coordinates copied inline),
and artwork ↔ artist. The venue record has no back-link to events; you find those by searching the venue name.

## Honesty notes: what is real and what is illustrative

- **The identifiers are illustrative, not real partner identifiers.** AusStage IRIs use
  `https://www.ausstage.edu.au/pages/{event,contributor,venue}/demo-…`, and DAAO artwork IRIs use
  `…/works/demo-…/`. They do not match real AusStage/DAAO record numbers and may not resolve. DAAO artist
  IRIs follow DAAO's `/bio/<name>/` URL pattern, but they were not checked against the live site.
  AusStage `subject_of` links point to the AusStage home page instead of a specific record.
- **The people, venues, works and productions are real**, and the descriptions are short summaries written
  for the demo. They are not quoted from AusStage, DAAO or any collection.
- **Dates and details are approximate.** If a precise date was not certain, the timespan covers the whole
  year, for example the 1971 *Removalists*, 1989/2010 *Diary of a Madman* and 2013 *Waiting for Godot*.
  Coordinates are approximate, at town or building level. Dimensions are given for three works only: The
  Pioneer's come from its Commons file page; those for Shearing the Rams and Fire's On are approximate and
  were not checked against the holding gallery. Holding institutions come from the Commons/Google Art
  Project metadata, except Tower Hill (Warrnambool Art Gallery), which was not checked. Cast lists name
  only a few principal performers.
- The Namatjira artwork (`daao_work_central_australian_landscape.json`) is a **representative
  placeholder**, not a specific catalogued work. It has no image because Namatjira's work is still in
  copyright.
- Event images show the **venue**, not the production (the image label starts with "Venue:").
- Getty AAT IDs are used only for common terms: names, descriptions, painting, performance, oil paint,
  canvas, watercolour, paper, height, width and centimetres. Other classifications use a plain `_label`.

## Images

All images are Wikimedia Commons thumbnails (960 px wide) served from `upload.wikimedia.org`. The licence
and author below were read from the Commons API (`extmetadata`) on 2026-10-30, and every thumbnail URL
returned HTTP 200 `image/jpeg` to a HEAD request on that day. Each record states the credit in
`representation[].digitally_shown_by[].referred_to_by` ("attribution statement"), together with the
Commons file page URL. The author names are copied from Commons and were not verified separately.
Records with no image show placeholders in the UI: the Belvoir St Theatre venue, Neil Armfield,
Eugene von Guérard, the Namatjira artwork, and the Diary of a Madman and Hamlet events at Belvoir.

| Used for | Commons file | Author (per Commons) | Licence |
|---|---|---|---|
| Union Theatre venue + 1955 event | [University Of Melbourne Student Union House.JPG](https://commons.wikimedia.org/wiki/File:University_Of_Melbourne_Student_Union_House.JPG) | Polly clip | CC BY-SA 3.0 |
| Sydney Opera House venue + 1973 event | [Sydney Opera House - Dec 2008.jpg](https://commons.wikimedia.org/wiki/File:Sydney_Opera_House_-_Dec_2008.jpg) | Diliff | CC BY-SA 3.0 |
| Princess Theatre venue + 1990 event | [Melbourne Princess Theatre.jpg](https://commons.wikimedia.org/wiki/File:Melbourne_Princess_Theatre.jpg) | Donaldytong | CC BY-SA 3.0 |
| Sydney Theatre venue + 2013 event | [Sydney in February 2026 - 30 Sydney theatre Dawes point.jpg](https://commons.wikimedia.org/wiki/File:Sydney_in_February_2026_-_30_Sydney_theatre_Dawes_point.jpg) | Xyxyzyz | CC0 |
| La Mama venue + 1971 event | [La Mama Theatre, Carlton, Victoria, Australia.jpg](https://commons.wikimedia.org/wiki/File:La_Mama_Theatre,_Carlton,_Victoria,_Australia.jpg) | Mat Connolley (Matnkat) | CC BY 2.5 |
| Hugo Weaving | [Hugo Weaving 2014.jpg](https://commons.wikimedia.org/wiki/File:Hugo_Weaving_2014.jpg) | Siebbi | CC BY 3.0 |
| Richard Roxburgh | [Richard Roxburgh 2013.jpg](https://commons.wikimedia.org/wiki/File:Richard_Roxburgh_2013.jpg) | Eva Rinaldi | CC BY-SA 2.0 |
| Geoffrey Rush | [Geoffrey Rush Cannes 2011.jpg](https://commons.wikimedia.org/wiki/File:Geoffrey_Rush_Cannes_2011.jpg) | Georges Biard | CC BY-SA 3.0 |
| David Williamson | [David Williamson 1972 (cropped).jpg](https://commons.wikimedia.org/wiki/File:David_Williamson_1972_(cropped).jpg) | Australian Information Service | Public domain |
| Ray Lawler (plaque, not a portrait) | [Ray Lawler plaque in Sydney Writers Walk.jpg](https://commons.wikimedia.org/wiki/File:Ray_Lawler_plaque_in_Sydney_Writers_Walk.jpg) | Snapandrattle33 | CC BY-SA 4.0 |
| Anthony Warlow | [Anthony Warlow (6640179479).jpg](https://commons.wikimedia.org/wiki/File:Anthony_Warlow_(6640179479).jpg) | Eva Rinaldi | CC BY-SA 2.0 |
| Albert Namatjira | [Albert Namatjira portrait.jpg](https://commons.wikimedia.org/wiki/File:Albert_Namatjira_portrait.jpg) | Unknown author | Public domain |
| Tom Roberts | [Tom Roberts at Curlew Camp.jpg](https://commons.wikimedia.org/wiki/File:Tom_Roberts_at_Curlew_Camp.jpg) | Rodney Cherry | Public domain |
| Arthur Streeton | [Arthur Streeton circa 1896.jpg](https://commons.wikimedia.org/wiki/File:Arthur_Streeton_circa_1896.jpg) | Rodney Cherry (attrib.) | Public domain |
| Frederick McCubbin | [Frederick McCubbin - Self-portrait, 1886.jpg](https://commons.wikimedia.org/wiki/File:Frederick_McCubbin_-_Self-portrait,_1886.jpg) | Frederick McCubbin | Public domain |
| Clarice Beckett | [Portrait of Clarice Beckett.jpg](https://commons.wikimedia.org/wiki/File:Portrait_of_Clarice_Beckett.jpg) | Unknown author | Public domain |
| Shearing the Rams | [Tom Roberts - Shearing the rams - Google Art Project.jpg](https://commons.wikimedia.org/wiki/File:Tom_Roberts_-_Shearing_the_rams_-_Google_Art_Project.jpg) | Tom Roberts | Public domain |
| Fire's On | [Arthur Streeton - Fire's on - Google Art Project.jpg](https://commons.wikimedia.org/wiki/File:Arthur_Streeton_-_Fire%27s_on_-_Google_Art_Project.jpg) | Arthur Streeton | Public domain |
| The Pioneer | [Frederick McCubbin - The pioneer - Google Art Project.jpg](https://commons.wikimedia.org/wiki/File:Frederick_McCubbin_-_The_pioneer_-_Google_Art_Project.jpg) | Frederick McCubbin | Public domain |
| Passing Trams | [Clarice Beckett - Passing trams - Google Art Project.jpg](https://commons.wikimedia.org/wiki/File:Clarice_Beckett_-_Passing_trams_-_Google_Art_Project.jpg) | Clarice Beckett | Public domain |
| Tower Hill | [Eugene von Guerard Tower Hill 1855 EXHI014644.jpg](https://commons.wikimedia.org/wiki/File:Eugene_von_Guerard_Tower_Hill_1855_EXHI014644.jpg) | Eugene von Guerard | Public domain |

CC BY / CC BY-SA images must stay credited wherever they are shown. The frontend should display the
attribution statement next to each image.
