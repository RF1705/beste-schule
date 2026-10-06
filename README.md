# beste.schule for Home Assistant

[![HACS](https://github.com/RF1705/beste-schule/actions/workflows/hacs.yml/badge.svg)](https://github.com/RF1705/beste-schule/actions/workflows/hacs.yml)
[![Hassfest](https://github.com/RF1705/beste-schule/actions/workflows/hassfest.yml/badge.svg)](https://github.com/RF1705/beste-schule/actions/workflows/hassfest.yml)
[![GitHub release](https://img.shields.io/github/v/release/RF1705/beste-schule)](https://github.com/RF1705/beste-schule/releases)
[![GitHub Downloads](https://img.shields.io/github/downloads/RF1705/beste-schule/total)](https://github.com/RF1705/beste-schule/releases)
[![License](https://img.shields.io/github/license/RF1705/beste-schule)](LICENSE)
[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-rf1705-yellow?logo=buymeacoffee)](https://buymeacoffee.com/rf1705)

Home Assistant integration for beste.schule timetables, absences, homework, exams, school notices, school time and grade averages.

This custom integration connects Home Assistant to [beste.schule](https://beste.schule/) with a Personal Access Token. It creates calendar entries for lessons, absences, homework, exams and school-wide notices, exposes the current school-time state and adds grade average sensors per subject.

## Features

- Timetable calendar with lessons from beste.schule
- Timetable history keeps past lessons from the setup day onward
- Absence calendar with all-day absence events
- Homework calendar from visible journal notes
- Exams calendar from visible journal notes
- School notices calendar for day-wide substitution notes
- Homework to-do list from visible journal notes
- School time binary sensor
- Current lesson and next lesson sensors
- Sick-days sensor
- Current school-year sensor
- Grade average sensors per subject
- Grade averages use beste.schule calculation rules and collection weights when available
- Class sensor
- Timetable JSON sensor for `fabel-smith/stundenplan-card`
- Options to enable or disable calendars and the homework to-do list
- Translations for English, German, Turkish, Polish and other common Home Assistant languages
- Support for multiple children in one beste.schule account

## Installation with HACS

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=RF1705&repository=beste-schule&category=integration)

1. Open the HACS repository link above.
2. Confirm that the repository is added as an integration.
3. Install `beste.schule` from HACS.
4. Restart Home Assistant.
5. Go to **Settings** -> **Devices & services** -> **Add integration**.
6. Search for `beste.schule`.
7. Paste your beste.schule Personal Access Token.

## Manual HACS repository setup

If the button does not work:

1. Open Home Assistant.
2. Go to **HACS** -> **Integrations**.
3. Open the three-dot menu and choose **Custom repositories**.
4. Add this repository URL:

   ```text
   https://github.com/RF1705/beste-schule
   ```

5. Select **Integration** as the category.
6. Install `beste.schule`, restart Home Assistant and add the integration from **Devices & services**.

## Personal Access Token

Create a token in your beste.schule user account:

1. Sign in to beste.schule.
2. Open your user account from your name in the top right corner.
3. Select **API** in the left menu.
4. Create a new token under **Personal Access Token**.
5. Copy the token and paste it into the Home Assistant setup dialog.

## Entities

The integration currently creates:

- `calendar`: timetable
- `calendar`: absences
- `calendar`: homework
- `calendar`: exams
- `calendar`: notices
- `todo`: homework
- `binary_sensor`: school time
- `sensor`: current lesson
- `sensor`: next lesson
- `sensor`: sick days
- `sensor`: class
- `sensor`: school year
- `sensor`: timetable card data
- `number`: timetable week offset for compatible dashboard cards
- `sensor`: grade average per subject

### Grade dashboard example

The grade average sensors can be displayed as a compact dashboard using
[Mushroom cards](https://github.com/piitaya/lovelace-mushroom).

The example below shows the current average for each subject and, when
available, the previous school year's average. If a subject did not exist in
the previous school year, the previous-year value is omitted automatically.
Subjects without a current grade are shown as `Noch keine Note`.


The example uses the following color scheme:

- up to `2.5`: green
- up to `3.5`: light green
- below `5.0`: orange
- `5.0` and worse: red
- no current grade: grey

The complete dashboard configuration is available in
[`examples/grade-dashboard.yaml`](examples/grade-dashboard.yaml).

The example YAML uses `sensor.test_note_*` entity IDs because the screenshot
was created with test sensors. Replace those IDs with the grade sensor entity
IDs created for your child, for example `sensor.<child>_note_ethik`.

The previous school year is read from the corresponding sensor attribute. The
template checks whether that attribute exists before displaying it, so subjects
introduced in the current school year work without any special handling.

### stundenplan-card compatibility

The `0.4` releases are compatible with [`fabel-smith/stundenplan-card`](https://github.com/fabel-smith/stundenplan-card) through JSON source. This is a nice way to show the beste.schule timetable as a compact visual table in a Home Assistant dashboard.

Use the `Timetable card` sensor from this integration in the card:

```yaml
type: custom:stundenplan-card
source_type: sensor
source_entity: sensor.<child>_stundenplan_card
source_attribute: plan
source_time_key: Stunde
```

The legacy `plan` attribute keeps the existing behavior: it shows the current
Monday-Friday week on weekdays and switches to the upcoming week on Saturday
and Sunday. Cancelled lessons are included as `Ausfall: <subject>` cells.

Recent `stundenplan-card` releases can also navigate between weeks. For that
mode, use the card's integration/entity source in the visual editor and select
the same `Timetable card` sensor. The sensor additionally exposes
`rows_table`, date metadata and the matching `week_offset_entity`. The
generated `Timetable week offset` number supports the current week plus the
next two weeks; the card's arrow buttons update it automatically.

Existing dashboards that use `source_type: sensor`, `plan` and `Stunde`
continue to work unchanged.

Old test entities from early versions may remain in Home Assistant's entity registry after an update. They can be removed from **Settings** -> **Devices & services** -> **Entities** when they are no longer provided by the integration.

### Multiple children

Starting with `0.6`, one beste.schule token can create separate Home Assistant devices for multiple children from the same account. Each child gets its own calendars, sensors and homework to-do list.

## Roadmap

- More robust substitution details as the API shapes become clearer

## Support

This project is community-maintained and not affiliated with beste.schule.

If the integration helps you, you can support development here: [buymeacoffee.com/rf1705](https://buymeacoffee.com/rf1705).

## License

MIT
