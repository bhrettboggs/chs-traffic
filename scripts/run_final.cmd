@echo off
rem Rebuilds outputs\final\ (Task 3 final results) from a clean checkout, in Windows Command Prompt.
rem Usage: scripts\run_final.cmd            (from the repo folder)
rem Long: about 1.5-3 hours depending on cores. Every step can be stopped and run again; it resumes.
rem To start over, delete outputs\final\raw\ and the outputs\final\search_state_*.json files.
setlocal
cd /d "%~dp0.."
set /a W=%NUMBER_OF_PROCESSORS%-1
if %W% LSS 1 set W=1
py -3.11 scripts\02_build_graph.py || exit /b 1
py -3.11 scripts\05_join_widths.py || exit /b 1
py -3.11 scripts\13_final_results.py noise --workers %W% || exit /b 1
py -3.11 scripts\13_final_results.py backtest --workers %W% || exit /b 1
py -3.11 scripts\13_final_results.py city --workers %W% || exit /b 1
for %%S in (1 1.3 1.6) do (
  py -3.11 scripts\09_search.py --peak both --demand-scale %%S --max-rounds 20 --workers %W% --state outputs\final\search_state_both_x%%S.json --moves-out outputs\final\search_moves_x%%S.csv || exit /b 1
)
py -3.11 scripts\13_final_results.py pareto --workers %W% || exit /b 1
py -3.11 scripts\13_final_results.py report || exit /b 1
echo Done: outputs\final\RESULTS.md
