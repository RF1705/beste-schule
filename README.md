# beste.schule for Home Assistant

[![HACS](https://github.com/RF1705/beste-schule/actions/workflows/hacs.yml/badge.svg)](https://github.com/RF1705/beste-schule/actions/workflows/hacs.yml)
[![Hassfest](https://github.com/RF1705/beste-schule/actions/workflows/hassfest.yml/badge.svg)](https://github.com/RF1705/beste-schule/actions/workflows/hassfest.yml)
[![GitHub release](https://img.shields.io/github/v/release/RF1705/beste-schule)](https://github.com/RF1705/beste-schule/releases)
[![License](https://img.shields.io/github/license/RF1705/beste-schule)](LICENSE)
[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-rf1705-yellow?logo=buymeacoffee)](https://buymeacoffee.com/rf1705)

Read-only Home Assistant integration for beste.schule timetables, absences, school time and grade averages.

This custom integration connects Home Assistant to [beste.schule](https://beste.schule/) with a Personal Access Token. It creates calendar entries for lessons and absences, exposes the current school-time state and adds grade average sensors per subject.

## Features

- Timetable calendar with lessons from beste.schule
- Absence calendar with all-day absence events
- Homework calendar beta from visible journal notes
- School time binary sensor
- Current lesson and next lesson sensors
- Grade average sensors per subject
- Class sensor
- Beta timetable JSON sensor for `fabel-smith/stundenplan-card`
- English and German translations

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

If you registered with **Sign in with Apple**, sign in to beste.schule the same way in the browser first. The token is still created inside your beste.schule user account.

## Entities

The integration currently creates:

- `calendar`: timetable
- `calendar`: absences
- `calendar`: homework
- `binary_sensor`: school time
- `sensor`: current lesson
- `sensor`: next lesson
- `sensor`: class
- `sensor`: timetable card beta data
- `sensor`: grade average per subject

### stundenplan-card compatibility

The beta releases are compatible with [`fabel-smith/stundenplan-card`](https://github.com/fabel-smith/stundenplan-card) through its **Beliebiger Sensor (JSON)** source. This is a nice way to show the beste.schule timetable as a compact visual table in a Home Assistant dashboard.

Use the `Timetable card` sensor from this integration in the card:

```yaml
type: custom:stundenplan-card
source_type: sensor
source_entity: sensor.<child>_stundenplan_card
source_attribute: plan
source_time_key: Stunde
```

The sensor exposes a single `plan` attribute for the current Monday-Friday week. The week changes automatically based on the current date. Cancelled lessons are included as `Ausfall: <subject>` cells.

Old test entities from early versions may remain in Home Assistant's entity registry after an update. They can be removed from **Settings** -> **Devices & services** -> **Entities** when they are no longer provided by the integration.

## Roadmap

- Exam and classwork calendar entries
- More robust substitution details as the API shapes become clearer

## Support

This project is community-maintained and not affiliated with beste.schule.

If the integration helps you, you can support development here: [buymeacoffee.com/rf1705](https://buymeacoffee.com/rf1705).

## License

MIT
