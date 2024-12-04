from pathlib import Path

file_in  = "/home/xbmc/video_files_in.txt"
file_out = "/home/xbmc/video_files_out.txt"

with open(file_out, 'w', encoding='UTF-8') as _file_out:
    with open(file_in, 'r') as _file_in:
        for file in _file_in:
            _file = file.strip()
            if not Path(_file).is_file():
                _file_out.write("{}\n".format( _file ))