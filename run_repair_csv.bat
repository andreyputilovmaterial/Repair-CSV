@ECHO OFF


@REM :: link your files here
SET "INP_CSV=Outputs\R221366.csv"

@REM :: output file
SET "REPAIRED_CSV=Outputs\R221366.repaired.csv"




@REM :: adjust config options per your needs
@REM :: when using "if" in BAT files, "1==1" is true and "1==0" is false

@REM :: read first n columns (default is 10)
SET "CONFIG_MAX_COLUMNS=10"

@REM :: delimiter
SET "CONFIG_DELIMITER=,"

@REM :: threshold - limit rati, expressed in %'s, that the number of "correct" lines (matching signature) should exceed
SET "CONFIG_THRESHOLD=76"

@REM :: CSV Read ENgine: can be "basic", "text_advanced", or "csv_module". The last one is the default.
SET "CONFIG_READ_CSV_ENGINE=csv_module"

@REM :: Debugging only, should not be turned on live
SET "CONFIG_DEBUG_LINE_NUMBERS=1==0"








IF %CONFIG_DEBUG_LINE_NUMBERS% (
    SET "CONFIG_DEBUG= --debug-mode-features line_num_investigation"
) else (
    SET "CONFIG_DEBUG="
)




ECHO -
ECHO 1. call the repair csv script!
python repair_csv.py --input "%INP_CSV%"  --output "%REPAIRED_CSV%" --check-columns "%CONFIG_MAX_COLUMNS%" --delimiter "%CONFIG_DELIMITER%" --threshold "%CONFIG_THRESHOLD%" --csv-reader "%CONFIG_READ_CSV_ENGINE%" %CONFIG_DEBUG%
if %ERRORLEVEL% NEQ 0 ( echo ERROR: Failure && pause && goto CLEANUP && exit /b %ERRORLEVEL% )



@REM :: Sorry, I am a hater of "pause" statements, but I don't need this bat file anyway, I'll be caling the script directly
@REM :: so, enjoy, I added "pause" here for you
@REM :: have fun
pause

