# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/turbolooser/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      107 |       73 |     32% |32-34, 40-61, 66-67, 73-111, 116-125, 130-153, 163-167, 173-174, 197-198 |
| custom\_components/roommind/binary\_sensor.py                      |       37 |        0 |    100% |           |
| custom\_components/roommind/climate.py                             |      174 |        0 |    100% |           |
| custom\_components/roommind/config\_flow.py                        |       54 |        0 |    100% |           |
| custom\_components/roommind/const.py                               |      157 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      208 |        2 |     99% |    53, 85 |
| custom\_components/roommind/control/mpc\_controller.py             |     1064 |       55 |     95% |182-184, 190, 290-291, 297-298, 310-320, 635-637, 655-656, 690-693, 704-711, 724-725, 1130-1132, 1353, 1439-1451, 1576-1584, 1599, 1888-1896, 1929, 2243, 2245, 2256, 2258, 2263, 2268, 2290, 2292 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      211 |        0 |    100% |           |
| custom\_components/roommind/control/residual\_heat.py              |       24 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        1 |     99% |        72 |
| custom\_components/roommind/control/thermal\_model.py              |      442 |       17 |     96% |394, 863-878, 989, 1112, 1119-1123 |
| custom\_components/roommind/coordinator.py                         |     1187 |       74 |     94% |454-455, 788-791, 1087-1088, 1098, 1100, 1549, 1591, 1649, 1983-1986, 2099, 2125-2127, 2131-2137, 2141, 2150, 2171, 2176, 2178, 2181, 2184, 2225, 2230-2235, 2239, 2272, 2274, 2277, 2280, 2296-2297, 2366-2367, 2394-2395, 2397-2398, 2429, 2448, 2451, 2467, 2470, 2473, 2480, 2595, 2598-2599, 2643-2644, 2654-2655, 2784, 2804-2812, 2830-2831, 2846-2851, 2868-2869 |
| custom\_components/roommind/diagnostics.py                         |      166 |        0 |    100% |           |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/ac\_coil\_dry\_manager.py     |      246 |        0 |    100% |           |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      170 |        2 |     99% |  125, 203 |
| custom\_components/roommind/managers/cover\_manager.py             |      197 |        0 |    100% |           |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      168 |        2 |     99% |   74, 181 |
| custom\_components/roommind/managers/demand\_controller.py         |       52 |        0 |    100% |           |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       54 |        1 |     98% |        28 |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      122 |        4 |     97% |60, 68, 199, 205 |
| custom\_components/roommind/managers/mold\_manager.py              |       69 |        0 |    100% |           |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |       38 |        0 |    100% |           |
| custom\_components/roommind/managers/valve\_manager.py             |      112 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py           |       59 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |       93 |        0 |    100% |           |
| custom\_components/roommind/repairs.py                             |       15 |        0 |    100% |           |
| custom\_components/roommind/sensor.py                              |      112 |        0 |    100% |           |
| custom\_components/roommind/services/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py         |      165 |        0 |    100% |           |
| custom\_components/roommind/store.py                               |      184 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |       93 |        0 |    100% |           |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/device\_utils.py                 |      192 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      146 |        2 |     99% |     62-63 |
| custom\_components/roommind/utils/mold\_utils.py                   |       32 |        0 |    100% |           |
| custom\_components/roommind/utils/notification\_utils.py           |       50 |        0 |    100% |           |
| custom\_components/roommind/utils/presence\_utils.py               |       36 |        0 |    100% |           |
| custom\_components/roommind/utils/schedule\_utils.py               |      192 |        0 |    100% |           |
| custom\_components/roommind/utils/sensor\_utils.py                 |       29 |        1 |     97% |        25 |
| custom\_components/roommind/utils/temp\_utils.py                   |       26 |        0 |    100% |           |
| custom\_components/roommind/websocket\_api.py                      |      295 |        2 |     99% |   768-773 |
| **TOTAL**                                                          | **6859** |  **236** | **97%** |           |


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