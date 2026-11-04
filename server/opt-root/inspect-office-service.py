import subprocess,shlex,json
raw=subprocess.check_output(['systemctl','show','jarvis-web.service','-p','Environment','--value'],text=True)
values=dict(s.split('=',1) for s in shlex.split(raw) if '=' in s)
keys=['JARVIS_MEMORY_TRANSPORT','JARVIS_DB_HOST','JARVIS_DB_PORT','JARVIS_DB_PASSWORD_FILE','JARVIS_WEB_STATE_DIR','JARVIS_STATE_DIR']
print(json.dumps({k:values.get(k) for k in keys}))
