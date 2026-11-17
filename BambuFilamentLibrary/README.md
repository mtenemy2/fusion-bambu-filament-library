# Bambu Lab Filament Library for Autodesk Fusion

Bambu Lab 필라멘트 전 제품의 **색상(외관)**과 **물성(물리 재질)**을 Fusion에 한 번에 넣어 주는 스크립트입니다.
실행할 때마다 Bambu Lab 공식 데이터를 인터넷에서 받아 **새로 나온 필라멘트와 색상을 자동으로 추가**합니다.

*English below.*

---

## 무엇이 들어가나요
- **외관(Appearance)**: 색상마다 1개. Bambu 공식 HEX 색을 쓰고, 라인에 맞게 광택·무광·실크·반투명·메탈 질감을 적용
  - 이름 예: `Bambu PLA Basic - Jade White (제이드 화이트) [10100]` (대괄호 안 숫자는 Bambu 색상 코드)
- **물리 재질(Physical Material)**: 제품 라인마다 1개. 예: `Bambu PLA Basic`, `Bambu PETG HF`, `Bambu TPU 95A HF`, `Bambu PAHT-CF`
  - 밀도, 영률, 인장/항복강도, 전단탄성계수, 푸아송비, 열전도율, 비열, 열팽창계수
  - 재질 정보의 Comments 칸에 권장 노즐·베드 온도, 건조 조건, 열변형온도, 데이터 출처
- 모두 Fusion **즐겨찾기(Favorites)**에 등록되어 어떤 디자인에서든 사용 가능
- 포함 범위(2026-11 기준): PLA, PETG, ABS, ASA, TPU, PC, PA(나일론), PET-CF, PPS-CF, PVA, 서포트. 342색, 48개 라인

## 설치
1. 이 `BambuFilamentLibrary` 폴더를 통째로 아래 위치에 복사합니다.
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\Scripts\`
   - macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/`
   - 또는 Fusion에서 `Shift+S` → **Scripts and Add-Ins** → 스크립트 탭의 **+** (Script from my computer) → 이 폴더 선택
2. Fusion에서 `Shift+S` → **BambuFilamentLibrary** 선택 → **Run**

## 실행하면
1. 최신 Bambu 공식 색상표를 내려받습니다. 인터넷이 안 되면 폴더에 포함된 데이터를 씁니다.
2. 즐겨찾기와 비교해서 **아직 없는 색상 수**를 보여 주고 추가할지 묻습니다.
3. **Yes**를 누르면 새 디자인이 열리고 항목이 만들어져 즐겨찾기에 추가됩니다. 이미 있는 항목은 건너뜁니다.
4. 처음 실행하면 1~3분 정도 걸립니다. 다음부터는 새로 나온 색상만 추가하므로 빠릅니다.
5. "Recolor ..." 창에서 **Yes**를 누르고 Fusion을 종료하면, 흰색으로 보이던 즐겨찾기 썸네일이 실제 필라멘트 색으로 바뀝니다. Fusion API는 썸네일을 다시 그릴 수 없어서, Fusion이 꺼진 뒤 `Favorites.adsklib` 안의 썸네일 그림을 직접 칠합니다. 원본은 `Favorites.adsklib.before-bambu-thumbnails`로 백업됩니다.

새 필라멘트가 나왔는지 궁금할 때 **다시 실행**하기만 하면 됩니다.

## 사용법
- 바디 우클릭 → **Physical Material** → `Bambu PLA Basic` 지정 (무게·해석용)
- **Appearance**(단축키 `A`) → 즐겨찾기의 `Bambu PLA Basic - <색>` 을 바디에 끌어다 놓기 (화면 색)
- Fusion API는 재질에 외관을 연결할 수 없어서, 재질(라인별)과 색(색상별)을 나눠 두었습니다. Fusion에서 외관은 재질 위에 덮어쓰는 방식이라 정상적인 사용 방법입니다.

## 값이 바뀐 항목
Fusion API는 즐겨찾기 항목을 덮어쓰거나 지울 수 없습니다. 실행 화면에 "Outdated in Favorites"가 1 이상이면:
1. 스크립트 폴더의 `last_report.txt`에서 목록을 확인
2. 해당 항목을 즐겨찾기에서 우클릭 → 제거
3. 스크립트를 다시 실행하면 새 값으로 추가됩니다

## 설정 (BambuFilamentLibrary.py 상단)
| 이름 | 기본값 | 설명 |
|---|---|---|
| `ONLINE_UPDATE` | `True` | 실행 시 최신 색상표 다운로드 |
| `ADD_TO_FAVORITES` | `True` | 즐겨찾기에 추가 |
| `FAMILIES` | `None` | 특정 계열만: 예 `("PLA", "PETG")` |
| `TEST_MODE` | `False` | 계열·질감별 샘플 몇 개만 생성 |
| `RECOLOR_THUMBNAILS` | `True` | 흰색 썸네일을 실제 색으로 바꾸기 제안 |

## 데이터와 한계
- 색상: Bambu Studio 공식 `filaments_color_codes.json` (실행할 때 최신본 다운로드)
- 물성: Bambu Lab 공식 기술 데이터 시트(TDS) 35종을 미리 정리한 `tds_all.json`
  - TDS가 없는 라인은 가장 가까운 TDS 값 + Bambu Studio 프로파일 밀도 사용
  - 처음 보는 새 라인은 이름으로 계열과 질감을 추정하고, 같은 계열의 대표 TDS 값을 씀
  - PVA·서포트의 기계 물성, 그리고 푸아송비·열전도율·비열·열팽창계수는 Bambu가 공개하지 않아 일반 문헌값/추정값
- 그라데이션·멀티컬러 제품은 첫 번째 색만 사용. HEX는 화면용 근사치
- 비공식 도구이며 Bambu Lab, Autodesk와 관련이 없습니다. 출처와 라이선스는 `NOTICE.md` 참고

---

## English

Adds every Bambu Lab filament to Autodesk Fusion: one **Appearance per color** (official hex) and one **Physical Material per product line** (density, modulus, strength, thermal values from Bambu technical data sheets), all added to **Favorites**. Each run downloads Bambu's latest official color table, so new filaments are picked up automatically; it falls back to the bundled data offline.

**Install**: copy this `BambuFilamentLibrary` folder into Fusion's `API/Scripts` folder (Windows `%APPDATA%\Autodesk\Autodesk Fusion 360\API\Scripts\`, macOS `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/`), or add it with the **+** button in *Scripts and Add-Ins*. Then `Shift+S` → **BambuFilamentLibrary** → **Run**.

When asked, click **Yes** to recolor the white Favorites thumbnails: the fix runs right after you close Fusion (the API cannot re-render thumbnails, so the images inside `Favorites.adsklib` are tinted; a backup is kept).

**Run again any time** to add newly released colors; items already in Favorites are skipped. Fusion's API cannot overwrite Favorites, so if the dialog reports outdated entries, remove those listed in `last_report.txt` from Favorites and run again.

**Use**: assign `Bambu <line>` as the Physical Material (mass, simulation) and drag `Bambu <line> - <color>` from Appearance onto the body (look).

Unofficial; not affiliated with Bambu Lab or Autodesk. See `NOTICE.md` for sources and licenses.
