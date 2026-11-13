# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/turbolooser/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      134 |       78 |     42% |38-40, 46-70, 93-94, 100-138, 143-154, 170-193, 203-207, 213-214, 237-238 |
| custom\_components/roommind/binary\_sensor.py                      |       38 |        0 |    100% |           |
| custom\_components/roommind/climate.py                             |      420 |        0 |    100% |           |
| custom\_components/roommind/config\_flow.py                        |       54 |        0 |    100% |           |
| custom\_components/roommind/const.py                               |      196 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      232 |        2 |     99% |   81, 113 |
| custom\_components/roommind/control/direct\_valve.py               |      115 |        0 |    100% |           |
| custom\_components/roommind/control/mpc\_controller.py             |     1435 |       33 |     98% |249, 295-296, 371-372, 378-379, 391-401, 739-741, 759-760, 824-831, 1099, 2132, 2135, 2274-2283, 2298, 2730, 3209, 3211, 3222, 3224, 3229, 3234, 3256, 3258 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      306 |        0 |    100% |           |
| custom\_components/roommind/control/residual\_heat.py              |       34 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        1 |     99% |        72 |
| custom\_components/roommind/control/thermal\_model.py              |      480 |       16 |     97% |434, 943-951, 1198, 1205-1209 |
| custom\_components/roommind/coordinator.py                         |     1423 |       62 |     96% |515-516, 1241-1242, 1252, 1254, 1801, 1852, 1880-1881, 1932, 2332-2335, 2548, 2592, 2601, 2623, 2628, 2630, 2633, 2636, 2680, 2685-2690, 2694, 2734, 2736, 2739, 2742, 2768-2769, 2838-2839, 2866-2867, 2869-2870, 2901, 2920, 2923, 2939, 2942, 2945, 2952, 3067, 3070-3071, 3115-3116, 3126-3127, 3256, 3276-3284, 3302-3303, 3318-3323, 3340-3341 |
| custom\_components/roommind/deprecation.py                         |       56 |        0 |    100% |           |
| custom\_components/roommind/diagnostics.py                         |      231 |        0 |    100% |           |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/ac\_coil\_dry\_manager.py     |      248 |        0 |    100% |           |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      186 |        2 |     99% |  125, 223 |
| custom\_components/roommind/managers/cover\_manager.py             |      204 |        0 |    100% |           |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      243 |        1 |     99% |       197 |
| custom\_components/roommind/managers/demand\_controller.py         |       52 |        0 |    100% |           |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       71 |        0 |    100% |           |
| custom\_components/roommind/managers/head\_offset\_tracker.py      |       67 |        2 |     97% |    97, 99 |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      123 |        2 |     98% |   71, 211 |
| custom\_components/roommind/managers/mold\_manager.py              |       71 |        0 |    100% |           |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |       69 |        0 |    100% |           |
| custom\_components/roommind/managers/valve\_lead\_tracker.py       |      130 |        1 |     99% |       141 |
| custom\_components/roommind/managers/valve\_manager.py             |      112 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py           |       59 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |       93 |        0 |    100% |           |
| custom\_components/roommind/repairs.py                             |       15 |        0 |    100% |           |
| custom\_components/roommind/sensor.py                              |      113 |        0 |    100% |           |
| custom\_components/roommind/services/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py         |      176 |        0 |    100% |           |
| custom\_components/roommind/store.py                               |      194 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |       94 |        0 |    100% |           |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/area\_utils.py                   |       18 |        0 |    100% |           |
| custom\_components/roommind/utils/device\_utils.py                 |      218 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      146 |        2 |     99% |     62-63 |
| custom\_components/roommind/utils/mold\_utils.py                   |       33 |        0 |    100% |           |
| custom\_components/roommind/utils/notification\_utils.py           |       50 |        0 |    100% |           |
| custom\_components/roommind/utils/presence\_utils.py               |       49 |        0 |    100% |           |
| custom\_components/roommind/utils/schedule\_utils.py               |      211 |        0 |    100% |           |
| custom\_components/roommind/utils/sensor\_utils.py                 |       29 |        1 |     97% |        25 |
| custom\_components/roommind/utils/temp\_utils.py                   |       26 |        0 |    100% |           |
| custom\_components/roommind/websocket\_api.py                      |      342 |        3 |     99% |650, 882-887 |
| **TOTAL**                                                          | **8677** |  **206** | **98%** |           |


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