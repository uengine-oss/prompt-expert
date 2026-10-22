# prompt-expert

Windows용 생산성 도구입니다. 두 가지 기능을 담고 있습니다.

- **음성 받아쓰기**: MacWhisper의 "Alt 누르고 말하기"를 옮겼습니다. Alt를 누른 채 말하고 손을 떼면, 받아쓴 글자가 지금 커서가 있는 입력창에 들어갑니다.
- **Copy Path**: 예전 [copy-path](https://github.com/uengine-oss/copy-path) 도구를 통합했습니다. 탐색기에서 우클릭하면 파일·폴더 경로를 복사하고, 최근 경로를 다시 복사하거나 열 수 있습니다.

음성 인식은 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)로 PC 안에서 처리하며, 음성이 인터넷으로 전송되지 않습니다.

데모 영상: [demo/prompt-expert-demo.mp4](demo/prompt-expert-demo.mp4). 음성으로 AI 프롬프트를 쓰고 Copy Path로 파일 경로를 넣는 과정을 담았습니다(1080p, 92초, 내레이션 ElevenLabs).
이전 사용법 영상: [demo/winwhisper-usage.mp4](demo/winwhisper-usage.mp4). 이름 변경 전에 녹화했습니다.

## 설치

`prompt-expert-Setup-0.1.0.exe`를 실행합니다. 관리자 권한 없이 현재 사용자용으로 설치됩니다(`%LOCALAPPDATA%\Programs\prompt-expert`).
설치 중에 고를 수 있는 옵션은 다음과 같습니다.

| 옵션 | 기본 |
|---|---|
| 녹음 중 화면에 애니메이션 표시 (파형이 움직이는 작은 창) | 켜짐 |
| 탐색기 우클릭 메뉴에 Copy Path / Recent Paths / Open Paths 추가 | 켜짐 |
| Windows 시작 시 자동 실행 | 켜짐 |
| 가벼운 모델 사용 (small, 느린 PC 권장) | 꺼짐 |
| 바탕 화면에 바로 가기 만들기 | 꺼짐 |

제거는 "설정 → 앱" 또는 시작 메뉴의 제거 바로가기에서 합니다. 사용자 설정(`%APPDATA%\prompt-expert`)과 내려받은 모델(`%USERPROFILE%\.cache\huggingface`)은 남겨 둡니다.
설치 없이 쓰려면 `prompt-expert-0.1.0-portable.zip`의 압축을 풀고 `prompt-expert.exe`를 실행하세요.

## 사용법

1. 실행하면 작업 표시줄 트레이에 마이크 아이콘이 생깁니다. 처음 실행할 때는 모델을 내려받습니다(회색 아이콘).
2. 아이콘이 파란색이 되면 준비가 끝난 것입니다. 글자를 넣을 곳에 커서를 두고 **Alt를 누른 채 말한 뒤 손을 뗍니다.**

| 아이콘 | 상태 |
|---|---|
| 회색 | 모델 불러오는 중 |
| 파랑 | 대기 |
| 빨강 | 녹음 중 (Alt 누르고 있음) |
| 노랑 | 받아쓰는 중 |

- 녹음 애니메이션을 켜 두면 Alt를 누르는 동안 화면 아래 가운데에 빨간 점과 음량 파형, 경과 시간이 표시됩니다. Alt를 떼면 "받아쓰는 중"으로 바뀌고, 글자가 들어가면 사라집니다. 이 창은 포커스나 마우스 클릭을 가져가지 않습니다.
- Alt를 짧게 탭하거나 Alt+Tab, Alt+F4 같은 조합키를 쓰면 받아쓰기가 시작되지 않고 원래 기능대로 동작합니다.
- 텍스트는 클립보드에 넣은 뒤 Ctrl+V로 붙여넣습니다. 끝나면 원래 클립보드 내용을 복원하고, Win+V 클립보드 기록에도 남기지 않습니다.
- 받아쓰기 처리 중에는 추가 녹음을 받지 않습니다. 결과가 들어가고 표시가 사라진 뒤 다시 말하세요. 입력창을 바꾸거나 보조키를 계속 누르면 자동 입력 대신 결과를 클립보드에 보관하고 오류 알림을 표시합니다.
- 트레이 아이콘 우클릭 메뉴: 설정 파일 열기, 로그 폴더 열기, Windows 시작 시 실행, 녹음 애니메이션 표시, 탐색기 우클릭 메뉴 (Copy Path), 종료

## Copy Path (탐색기 우클릭 메뉴)

파일·폴더를 우클릭한 뒤 **더 많은 옵션 표시**(또는 Shift+F10 → W)를 선택하면 아래 메뉴가 나옵니다.

| 메뉴 | 동작 |
|---|---|
| Copy Path | 선택한 파일·폴더의 전체 경로를 따옴표 없이 복사합니다. 폴더 빈 공간에서 누르면 현재 폴더 경로를 복사합니다. |
| Recent Paths | 최근 복사한 10개 경로 중 하나를 다시 복사합니다. |
| Open Paths | 최근 경로의 파일은 기본 앱으로, 폴더는 탐색기로 엽니다. |

- 같은 경로는 하나만 남고, 다시 복사하면 목록 맨 앞으로 옵니다. 목록에는 파일 이름과 경로 앞부분만 보이지만, 복사되는 경로는 줄이지 않습니다.
- 복사에 성공해도 알림이나 소리는 없습니다. 실패하면 `%APPDATA%\prompt-expert\last-error.txt`에 이유가 남습니다.
- 기록은 `%APPDATA%\prompt-expert\path-history.json`에만 저장됩니다. 이 기능은 상주하지 않고 메뉴를 누를 때만 잠깐 실행됩니다.
- 예전 PowerShell 버전 CopyPath가 깔려 있으면, 설치할 때 그 메뉴는 지우고(중복 방지) 최근 경로 기록은 가져옵니다.
- 트레이 메뉴 "탐색기 우클릭 메뉴 (Copy Path)"로 켜고 끌 수 있습니다.

## 설정 (`%APPDATA%\prompt-expert\config.json`)

| 키 | 기본값 | 설명 |
|---|---|---|
| `hotkey` | `"alt"` | `alt`(좌우 모두), `left_alt`, `right_alt`, `ctrl`, `right_ctrl`, `f13`, `f14`, 또는 `"0x7E"` 같은 가상 키 코드 |
| `min_hold_seconds` | `0.35` | 이 시간보다 짧게 누르면 탭으로 보고 무시 |
| `model` | `"large-v3-turbo"` | CUDA 사용 시 기본 모델. 자동 장치 선택에서 CPU만 사용 가능하면 `cpu_model`을 사용합니다. 그 밖에 직접 지정한 모델은 유지합니다 |
| `device` / `compute_type` | `"auto"` | NVIDIA GPU가 있으면 CUDA float16, 없으면 CPU int8 |
| `cpu_model` | `"small"` | 기본 대형 모델을 CPU에서 자동 실행할 때 사용할 경량 모델. 기존 설정에도 적용됩니다. `null`이면 대형 모델을 유지합니다. 최초 사용 시 다운로드가 필요하며 모델에 따라 인식 정확도가 달라집니다 |
| `beam_size` | `1` | 빠른 받아쓰기를 위한 탐색 폭. `5`로 높이면 처리 시간이 늘어날 수 있습니다 |
| `language` | `"auto"` | 자동 감지. 한국어로 고정하려면 `"ko"` |
| `initial_prompt` | `""` | 자주 쓰는 고유명사나 용어를 넣으면 인식률이 올라갑니다 |
| `paste_method` | `"clipboard"` | `"type"`이면 클립보드를 쓰지 않고 유니코드 키 입력으로 넣습니다 |
| `sounds` | `true` | 녹음 시작과 끝을 알리는 효과음 |
| `overlay` | `true` | 녹음과 받아쓰기 중에 화면 애니메이션 표시 |
| `input_device` | `null` | 마이크 장치 이름이나 번호. `null`이면 기본 장치 |

설정을 바꾼 뒤에는 트레이 메뉴에서 종료하고 다시 실행하세요.

## 소스에서 실행 / 빌드 (Windows)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m winwhisper            # 트레이 앱
.\.venv\Scripts\python -m winwhisper --transcribe sample.wav
.\build.ps1                                      # dist\prompt-expert\prompt-expert.exe
.\installer\build_installer.ps1                  # dist\prompt-expert-Setup-<버전>.exe (Inno Setup 6, 없으면 자동 설치)
```

소스에서 실행할 때 `ctranslate2.dll`을 불러오지 못하면 [Visual C++ 재배포 패키지(x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)를 설치하세요. `build.ps1`로 만든 exe에는 이 런타임이 포함되어 있습니다.

## 테스트

- 단위 테스트(어느 OS에서나): `python -m unittest discover -s tests -t .`
  Alt 길게 누르기, 탭, Alt+Tab, Alt+Shift 같은 키 판정을 검사합니다.
- Windows E2E: `powershell -File tests\run_e2e.ps1 -Case ko [-AppExe dist\prompt-expert\prompt-expert.exe]`
  WAV 파일을 마이크 대신 쓰고, 실제 Alt 키 입력을 저수준 훅으로 흘려보냅니다. 그 뒤 다음을 검사합니다.
  - 탭은 무시되는지
  - 녹음 애니메이션 창이 뜨는지
  - 받아쓴 글자가 Tk 입력창과 메모장에 들어가는지
  - 포커스가 유지되는지
  - 클립보드가 복원되는지

- Copy Path E2E: `powershell -File tests\run_e2e.ps1 -Suite copypath [-AppExe ...]`
  탐색기와 똑같이 레지스트리의 명령줄을 실행해 다음을 검사합니다.
  - 파일, 폴더, 드라이브 루트, 폴더 빈 공간 경로 복사 (한글·공백·`&` 포함)
  - 최근 경로의 순서와 중복 제거, 다시 복사, 기본 앱으로 열기
  - 예전 CopyPath 메뉴 정리와 기록 가져오기, 메뉴 제거

  두 E2E 모두 반드시 로그인한 데스크톱 세션에서 실행해야 합니다. 그래서 스크립트가 대화형 예약 작업으로 실행합니다.

### Mac에서 Windows 테스트 VM 쓰기 (Apple Silicon)

[vm/vm.sh](vm/vm.sh)는 QEMU와 HVF 가속으로 Windows 11 ARM64를 돌립니다. 이미지는 Microsoft 공식 Enterprise 평가판(90일)입니다.
앱은 이 VM 안에서 x64 Python과 x64 exe로, Windows의 x64 에뮬레이션 위에서 테스트합니다.

```bash
vm/vm.sh install        # 최초 1회: autounattend.xml로 무인 설치 + SSH 설정 (~15분)
vm/vm.sh start          # 부팅
open vnc://127.0.0.1:5905   # 화면 보기
vm/vm.sh ssh            # PowerShell (ww / WinWhisper1!)
vm/vm.sh shot a.png     # 스크린샷
vm/vm.sh stop
```

ISO와 디스크 파일은 `~/winwhisper-vm/`에 있습니다.

사용법 영상은 `demo/start_app.ps1`(VM)로 앱을 띄우고, `demo/record.py`로 녹화한 뒤, `demo/compose.py`로 편집해 다시 만들 수 있습니다.

데모 영상(`demo/prompt_demo/`)은 다음 순서로 다시 만들 수 있습니다.
1. `ELEVENLABS_API_KEY=... python demo/elevenlabs_tts.py <voice_id> <tts폴더> demo/prompt_demo/narration.json`으로 내레이션과 말소리를 만듭니다.
2. VM에서 `scene.ps1`을 데스크톱 세션으로 실행합니다(프롬프트 창, 탐색기, 앱 배치).
3. `record.py`로 마우스와 키를 조작하며 녹화합니다. 마우스는 QMP로 움직이므로 `vm.sh`가 `qmp.sock`을 열어 둬야 합니다.
4. `compose.py`로 편집합니다.
