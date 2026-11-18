# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/turbolooser/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      153 |       83 |     46% |41-43, 49-76, 99-100, 106-144, 149-164, 180-203, 238-242, 248-249, 268-269 |
| custom\_components/roommind/binary\_sensor.py                      |       78 |        0 |    100% |           |
| custom\_components/roommind/climate.py                             |      400 |        0 |    100% |           |
| custom\_components/roommind/config\_flow.py                        |       54 |        0 |    100% |           |
| custom\_components/roommind/const.py                               |      237 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      242 |        2 |     99% |   83, 115 |
| custom\_components/roommind/control/direct\_valve.py               |      226 |       24 |     89% |311-319, 342-343, 347-352, 358-360, 384-385, 415-416 |
| custom\_components/roommind/control/mpc\_controller.py             |     1672 |       46 |     97% |320, 366-367, 445-446, 452-453, 465-475, 909-911, 995-1002, 1303, 2230, 2470, 2473, 2603-2605, 2630-2632, 2634-2644, 2673, 2872-2874, 2980-2982, 3007-3009, 3664, 3666, 3677, 3679, 3684, 3689, 3711, 3713 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      427 |        0 |    100% |           |
| custom\_components/roommind/control/residual\_heat.py              |       48 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        1 |     99% |        72 |
| custom\_components/roommind/control/thermal\_model.py              |      574 |        2 |     99% | 531, 1345 |
| custom\_components/roommind/coordinator.py                         |     1874 |       54 |     97% |656-657, 1625-1626, 1636, 1638, 2299, 2360, 2389-2390, 2441, 2650, 2896-2899, 3191-3192, 3329, 3338, 3360, 3365, 3367, 3373, 3522, 3527-3532, 3536, 3718-3719, 3746-3747, 3749-3750, 3781, 3800, 3803, 3819, 3822, 3825, 3832, 3947, 3950-3951, 3995-3996, 4006-4007, 4159, 4214-4215, 4230-4235, 4252-4253 |
| custom\_components/roommind/deprecation.py                         |       56 |        0 |    100% |           |
| custom\_components/roommind/diagnostics.py                         |      243 |        0 |    100% |           |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/ac\_coil\_dry\_manager.py     |      252 |        0 |    100% |           |
| custom\_components/roommind/managers/air\_quality\_manager.py      |      128 |        0 |    100% |           |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      261 |        3 |     99% |144, 307, 329 |
| custom\_components/roommind/managers/cover\_manager.py             |      227 |        0 |    100% |           |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      297 |        1 |     99% |       213 |
| custom\_components/roommind/managers/decision\_log.py              |      203 |        6 |     97% |219, 228-231, 282 |
| custom\_components/roommind/managers/demand\_controller.py         |       52 |        0 |    100% |           |
| custom\_components/roommind/managers/device\_setpoint\_tracker.py  |      102 |        0 |    100% |           |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       71 |        0 |    100% |           |
| custom\_components/roommind/managers/head\_offset\_tracker.py      |       67 |        2 |     97% |    97, 99 |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      126 |        2 |     98% |   69, 202 |
| custom\_components/roommind/managers/mold\_manager.py              |       86 |        0 |    100% |           |
| custom\_components/roommind/managers/price\_manager.py             |       87 |        0 |    100% |           |
| custom\_components/roommind/managers/recent\_temps.py              |       66 |        0 |    100% |           |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |      202 |        4 |     98% |150, 153, 222-223 |
| custom\_components/roommind/managers/valve\_lead\_tracker.py       |      130 |        1 |     99% |       141 |
| custom\_components/roommind/managers/valve\_manager.py             |      112 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py           |       59 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |       93 |        0 |    100% |           |
| custom\_components/roommind/repairs.py                             |       15 |        0 |    100% |           |
| custom\_components/roommind/sensor.py                              |      114 |        0 |    100% |           |
| custom\_components/roommind/services/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py         |      228 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_stats.py           |      205 |        4 |     98% |80, 109, 117, 159 |
| custom\_components/roommind/services/model\_backtest.py            |       77 |        0 |    100% |           |
| custom\_components/roommind/store.py                               |      194 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |      114 |        0 |    100% |           |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/area\_utils.py                   |       36 |        0 |    100% |           |
| custom\_components/roommind/utils/device\_utils.py                 |      236 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      186 |        2 |     99% |     98-99 |
| custom\_components/roommind/utils/mold\_utils.py                   |       31 |        0 |    100% |           |
| custom\_components/roommind/utils/notification\_utils.py           |       76 |        0 |    100% |           |
| custom\_components/roommind/utils/presence\_utils.py               |       49 |        0 |    100% |           |
| custom\_components/roommind/utils/price\_utils.py                  |      201 |        2 |     99% |   90, 176 |
| custom\_components/roommind/utils/schedule\_utils.py               |      281 |        3 |     99% |   419-421 |
| custom\_components/roommind/utils/sensor\_utils.py                 |       29 |        1 |     97% |        25 |
| custom\_components/roommind/utils/temp\_utils.py                   |       26 |        0 |    100% |           |
| custom\_components/roommind/websocket\_api.py                      |      397 |        3 |     99% |762, 1004-1009 |
| **TOTAL**                                                          | **11481** |  **246** | **98%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/turbolooser/roommind/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/turbolooser/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/turbolooser/roommind/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/turbolooser/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fturbolooser%2Froommind%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/turbolooser/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.