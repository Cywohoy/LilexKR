## LilexKR
[Lilex](https://github.com/mishamyrt/lilex)를 기반으로 [IBM Plex Sans KR](https://www.ibm.com/plex/)의 한글 글리프를 합쳤습니다. 따라서 Ligature(합자)을 지원하는 자연스러운 한글 고정폭 글꼴을 체험할 수 있습니다. 특히, 한글과 한글 사이에 놓인 Ligature (가 => 나 등)을 정상적으로 지원합니다.

## 구성
| 폰트명 | 반각 문자(ASCII) 너비 | 한글 너비 | 고정폭 여부 | Ligature 지원 |
| -- | -- | -- | -- | -- |
| IBM Plex Mono | 600 | – | O | X |
| IBM Plex Sans KR | 가변폭 | 892 | X | X |
| Lilex | 600 | – | O | O |
| Monoplex KR | 528 | 1056 | O | X |
| Monoplex KR Wide | 600 | 1000 | O | X |
| **LilexKR Std** | 600 | 1200 | O | O |
| **LilexKR 528** | 528 | 1056 | O | O |
| **LilexKR 35** | 600 | 1000 | X (3:5 비율) | O |

한글이 주로 쓰이는 환경에서는 **LilexKR 528**이, 주석 등의 제한적인 부분만 한글로 사용하는 환경에서는 **LilexKR Std** 혹은 **Lilex KR 35**를 사용하는 것이 가독성이 좋습니다. **LilexKR 35**는 **LilexKR Std**보다 한글의 자간이 좁아 가독성 측면에서 나으나, 완전한 1:2 비율 고정폭 글꼴이 아니기에 줄이 똑바르지 않은 곳이 존재할 수 있습니다.

## 라이선스
Lilex KR 시리즈는 SIL Open Font License 1.1에 따라 배포됩니다.

이 프로젝트는 다음의 원본 폰트들을 기반으로 제작되었습니다:
 * Lilex: Copyright (c) 2019, The Lilex Project Authors (OFL 1.1; https://github.com/mishamyrt/Lilex/blob/master/OFL.txt)
 * IBM Plex Sans KR: Copyright (c) 2017, IBM Corp. with Reserved Font Name "Plex" (OFL 1.1; https://github.com/IBM/plex/blob/master/LICENSE.txt)

허용 범위
 - 개인 및 상업적 용도: 웹사이트, 인쇄물, 로고, 소프트웨어 등에 자유롭게 사용 가능합니다.
 - 수정 및 재배포: 폰트의 글리프를 수정하거나 다른 폰트와 병합하여 재배포할 수 있습니다.

제한 사항
 - 폰트 판매 금지: 폰트 파일(.ttf / .otf) 자체를 유료로 판매하는 행위는 엄격히 금지됩니다.
 - 저작권 유지: 수정 및 재배포 시 원본 폰트 제작자의 저작권 고지문을 반드시 포함해야 합니다.

## 업데이트
### v1.001
- 한글 글리프가 Bounding box를 약간 벗어나 크게 렌더되는 문제 수정
- 한글 글리프의 위치가 어색했던 문제 수정

### v1.002
- 한글 글리프의 baseline을 라틴 글리프에 맞도록 수정
- 라틴 글리프의 힌팅 이슈 수정

### v1.003
- 한글 글리프의 높이를 힌팅된 라틴 글리프에 맞도록 수정
- 라틴 글리프의 높이가 잘못된 문제 수정

### v1.004
- 한글 글리프를 10% 확대

### v1.005
- 한글 글리프 및 라틴 글리프의 크기 조정
- 힌팅 조정
- 1080 패밀리의 라틴 글리프의 폭 확대