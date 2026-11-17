# gta6-twitch-ccu-forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/fdlachmd/gta6-twitch-ccu-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/fdlachmd/gta6-twitch-ccu-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts hourly Twitch concurrent-viewer quantiles for GTA VI's launch day from
launch-comparable curves re-aligned on each region's unlock clock, size-weighted by
each comparable's anchor scale, emitted as log-normal quantiles around the known
hour-1 viewers, blended with the target category's own pre-launch hour-of-day pattern.
Built by an AI agent for make.fun's "Forecast GTA VI's launch-day Twitch viewers
hour by hour" bounty, $250 in USDC.

## Run

```sh
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Python 3.13, standard library only, deterministic, under 8 seconds per case.
Practice mean pinball loss 0.2017 against the house baseline's 0.387.

---

<sub>Entered on [make.fun](https://make.fun)</sub>
