GigaAM Transcriber {version}
============================

Расшифровка русской речи из аудио- и видеофайлов моделями GigaAM v3.
Работает без интернета. Установка не нужна: распакуйте папку целиком.

Запуск
------
GigaAmTranscriber.exe - окно программы. Нажмите "+ Добавить" или перетащите
файлы (или папку) в окно: они распознаются по очереди, текст появляется по ходу.
Модель начинает загружаться сразу при запуске и остаётся в памяти между файлами.
Текст сохраняется рядом с исходным файлом: имя-transcript.txt и
имя-transcript-timestamps.txt (в настройках можно добавить SRT и JSON).
Окну нужен Microsoft Edge WebView2 Runtime; в Windows 10 и 11 он обычно уже есть,
а если его нет, программа предложит открыть страницу загрузки.

gigaam-cli.exe - командная строка, например:
    gigaam-cli.exe запись.mp3
    gigaam-cli.exe *.mp4 --formats txt,srt --out-dir C:\Тексты
    gigaam-cli.exe лекция.m4a --model CTC --device cpu
Полный список параметров: gigaam-cli.exe --help

Видеокарта
----------
Устройство "Авто" использует любую видеокарту с DirectX 12 (NVIDIA, AMD, Intel)
через DirectML, а если её нет - процессор. Отдельные драйверы CUDA не нужны.

Содержимое папки
----------------
_internal\                   библиотеки программы
models\                      модели RNNT и CTC и модель поиска речи Silero VAD
ffmpeg.exe                   чтение аудио и видео (FFmpeg, лицензия GPLv3)
gigaam-config.example.json   пример настроек; переименуйте в gigaam-config.json,
                             чтобы изменить параметры поиска речи
licenses\                    лицензии всех компонентов
THIRD_PARTY_NOTICES.md       список компонентов и ссылки на исходный код

Не удаляйте и не переносите по отдельности _internal, models и ffmpeg.exe.

English
-------
Offline Russian speech recognition with GigaAM v3. Run GigaAmTranscriber.exe for
the window or gigaam-cli.exe for the command line (gigaam-cli.exe --help).
"Auto" uses any DirectX 12 GPU through DirectML and falls back to the CPU.
Licences of all bundled components are in the licenses folder.
