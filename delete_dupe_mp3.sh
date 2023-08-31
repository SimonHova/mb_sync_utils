#!/bin/sh
find /media/Take/Music/ -regextype posix-extended -regex '^.* \(([0-9]?[0-9])\)\.(flac|mp3)' -delete
