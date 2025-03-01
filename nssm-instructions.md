# Running a Python Script as a Windows Service using NSSM




## 1. Build the Executable
To convert the script into an executable, use `pyinstaller`:

```sh
venv\Scripts\pyinstaller -F [YOUR_SCRIPT]
```

## 2. Install NSSM
Download NSSM from the official website, extract it to a folder of your choice, and add the folder to your `PATH` environment variable.

## HOW TO ADD TO PATH
FIND THE PATH TO THE WIN64 .exe file for nssm 

```sh
setx PATH "%PATH%;C:\nssm-2.24\win64" /M
```

THEN TO VERIFY 
```sh
nssm --version
```


## 3. Run Command Prompt as Administrator
To ensure you have the necessary permissions, open a terminal with administrative privileges.

## 4. Navigate to the Script Location
Change the directory to where the executable is stored:

```sh
cd [PATH_TO_PROJECT]
```

## 5. Install and Start the Service
Use NSSM to install and start the service:

```sh
nssm.exe install [NAME OF SERVICE] [PATH TO SCRIPT.EXE]
nssm.exe start [NAME OF SERVICE]
```

## 6. Debugging Issues
If issues arise, redirect standard error output to a log file for debugging:

```sh
nssm set [NAME OF SERVICE] AppStderr [PATH OF PROJECT]\service-error.log
```

NSSM ensures that your service runs in the background, and if it crashes, you can check the logs to diagnose issues.
