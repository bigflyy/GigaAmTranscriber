GigaAM Transcriber {version} for Linux
======================================

Расшифровка русской речи из аудио- и видеофайлов моделями GigaAM v3.
Работает без интернета. Установка не нужна: распакуйте папку целиком.

    tar -xzf GigaAmTranscriber-v{version}-linux-x64.tar.gz
    ./GigaAmTranscriber/GigaAmTranscriber

Что нужно в системе
-------------------
Linux x86-64 с glibc 2.39 или новее (Ubuntu 24.04, Debian 13, Fedora 40 и новее),
FFmpeg и, для окна, WebKitGTK 4.1:
    Ubuntu, Debian: sudo apt install ffmpeg gir1.2-webkit2-4.1
    Fedora:         sudo dnf install ffmpeg-free webkit2gtk4.1 gobject-introspection
Если WebKitGTK нет, окно не откроется и программа напишет, что установить;
командная строка работает и без него.

Запуск
------
GigaAmTranscriber - окно программы. Нажмите "+ Добавить" или перетащите файлы
(или папку) в окно: они распознаются по очереди, текст появляется по ходу.
Текст сохраняется рядом с исходным файлом: имя-transcript.txt и
имя-transcript-timestamps.txt (в настройках можно добавить Markdown, SRT и JSON).

gigaam-cli - командная строка, например:
    ./gigaam-cli запись.mp3
    ./gigaam-cli *.mp4 --formats txt,srt --out-dir ~/Тексты
    ./gigaam-cli лекция.m4a --model CTC
Полный список параметров: ./gigaam-cli --help

Распознавание идёт на процессоре (видеокарты NVIDIA в Linux-версии пока нет;
для них есть Docker-образ с CUDA, см. DOCKER.md в репозитории).

Содержимое папки
----------------
_internal/                   библиотеки программы (Python, ONNX Runtime, PyGObject)
models/                      модели RNNT и CTC и модель поиска речи Silero VAD
gigaam-config.example.json   пример настроек; переименуйте в gigaam-config.json,
                             чтобы изменить параметры поиска речи
licenses/                    лицензии всех компонентов
THIRD_PARTY_NOTICES.md       список компонентов и ссылки на исходный код

Не удаляйте и не переносите по отдельности _internal и models.

English
-------
Offline Russian speech recognition with GigaAM v3, on the CPU. Needs glibc 2.39+,
FFmpeg and, for the window, WebKitGTK 4.1 (Ubuntu/Debian: sudo apt install ffmpeg
gir1.2-webkit2-4.1). Run ./GigaAmTranscriber for the window or ./gigaam-cli for the
command line (./gigaam-cli --help). Licences of all bundled components are in licenses/.
