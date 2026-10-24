# Blind World Hub

The website [blindworldhub.github.io](https://blindworldhub.github.io): accessible apps, guides and video reviews
for blind and visually impaired people, shared by Waqas.

## How content gets on the site

Everything is published by itself, about two minutes after a change.

- **Apps and files:** open [blindworldhub.github.io/add-app/](https://blindworldhub.github.io/add-app/), fill in the
  form, press Continue to GitHub, attach the file and press Publish release. Each release is one version of an app.
  To change or delete an app, edit or delete its release under Releases.
- **Guides and news:** [blindworldhub.github.io/write/](https://blindworldhub.github.io/write/) opens a new issue with
  the label `guide` or `news`. Closing the issue removes the article. Articles can also be Markdown files in
  `source/content/guides` and `source/content/news`.
- **Videos:** new videos on the YouTube channel appear by themselves (checked every six hours). Older videos:
  [blindworldhub.github.io/add-video/](https://blindworldhub.github.io/add-video/) opens an issue with the label `video`.
- **Fixed pages** (About, Contact, policies): `source/content/pages`. Settings such as links: `source/site.json`.

Only issues opened by the owner account are published. The owner tools are listed at
[blindworldhub.github.io/admin/](https://blindworldhub.github.io/admin/).

## How it is built

`source/tools/build.py` (plain Python, no packages) reads the releases, issues and the YouTube feed and writes the site to
`_site/`; `.github/workflows/publish.yml` runs it and copies the result to the top of this repository, which GitHub Pages serves. Do not edit those files by hand. Test locally with
`python3 source/tools/build.py --offline`.

Font: Atkinson Hyperlegible by the Braille Institute (SIL Open Font License, `source/static/assets/fonts/OFL.txt`).
Globe land shapes: Natural Earth (public domain).
