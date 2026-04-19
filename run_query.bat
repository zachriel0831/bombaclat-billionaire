@echo off
cd /d D:\work_space\stock\data-collecting
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
echo Running daily DB analysis...
python -X utf8 query_today.py > query_output.txt 2>&1
echo Done! Output saved to query_output.txt
