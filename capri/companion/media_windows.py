"""Read Windows playback metadata and window/monitor geometry, never media pixels."""
import asyncio
import ctypes
from ctypes import wintypes as wt
import os
from pathlib import PureWindowsPath

def windows_snapshot():
    if os.name!='nt':return []
    user=ctypes.WinDLL('user32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    user.GetForegroundWindow.restype=wt.HWND
    user.IsWindowVisible.argtypes=[wt.HWND]
    user.IsIconic.argtypes=[wt.HWND]
    user.GetWindowRect.argtypes=[wt.HWND,ctypes.POINTER(wt.RECT)]
    user.GetWindowThreadProcessId.argtypes=[wt.HWND,ctypes.POINTER(wt.DWORD)]
    user.GetWindowTextLengthW.argtypes=[wt.HWND]
    user.GetWindowTextW.argtypes=[wt.HWND,wt.LPWSTR,ctypes.c_int]
    user.MonitorFromWindow.argtypes=[wt.HWND,wt.DWORD]
    user.MonitorFromWindow.restype=wt.HANDLE
    class MonitorInfo(ctypes.Structure):
        _fields_=[('size',wt.DWORD),('monitor',wt.RECT),('work',wt.RECT),('flags',wt.DWORD)]
    user.GetMonitorInfoW.argtypes=[wt.HANDLE,ctypes.POINTER(MonitorInfo)]
    kernel.OpenProcess.argtypes=[wt.DWORD,wt.BOOL,wt.DWORD]
    kernel.OpenProcess.restype=wt.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[wt.HANDLE,wt.DWORD,wt.LPWSTR,ctypes.POINTER(wt.DWORD)]
    kernel.CloseHandle.argtypes=[wt.HANDLE]
    foreground=user.GetForegroundWindow()
    result=[]
    @ctypes.WINFUNCTYPE(wt.BOOL,wt.HWND,wt.LPARAM)
    def visit(hwnd,_):
        if not user.IsWindowVisible(hwnd) or user.IsIconic(hwnd):return True
        pid=wt.DWORD()
        user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value==os.getpid():return True
        length=user.GetWindowTextLengthW(hwnd)
        if not length:return True
        title=ctypes.create_unicode_buffer(min(length+1,2048))
        user.GetWindowTextW(hwnd,title,len(title))
        rect=wt.RECT()
        if not user.GetWindowRect(hwnd,ctypes.byref(rect)) or rect.right-rect.left<150 or rect.bottom-rect.top<100:return True
        info=MonitorInfo();info.size=ctypes.sizeof(info)
        monitor=user.MonitorFromWindow(hwnd,2)
        if not user.GetMonitorInfoW(monitor,ctypes.byref(info)):return True
        handle=kernel.OpenProcess(0x1000,False,pid.value)
        path=''
        if handle:
            try:
                buf=ctypes.create_unicode_buffer(32768);size=wt.DWORD(len(buf))
                if kernel.QueryFullProcessImageNameW(handle,0,buf,ctypes.byref(size)):path=buf.value
            finally:kernel.CloseHandle(handle)
        exe=PureWindowsPath(path).name.lower()
        bounds=info.monitor
        covers=(rect.left<=bounds.left+8 and rect.top<=bounds.top+8 and rect.right>=bounds.right-8 and rect.bottom>=bounds.bottom-8)
        game_path=any(token in path.lower() for token in ('steamapps\\common','epic games\\','riot games\\','xboxgames\\','battle.net\\'))
        excluded=exe in ('orca.exe','code.exe','windowsterminal.exe','powershell.exe','pwsh.exe','explorer.exe','pythonw.exe','python.exe')
        result.append({'app':exe,'title':title.value[:250],'origin':[bounds.left,bounds.top],
                       'game':game_path and not excluded,
                       'fullscreen':bool(covers and not excluded and (hwnd==foreground or game_path)),
                       'foreground':hwnd==foreground})
        return True
    user.EnumWindows.argtypes=[ctypes.c_void_p,wt.LPARAM]
    user.EnumWindows(visit,0)
    return result

async def playback_snapshot():
    from winrt.windows.media.control import (GlobalSystemMediaTransportControlsSessionManager as Manager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status)
    from winrt.windows.media import MediaPlaybackType
    async with asyncio.timeout(4):
        manager=await Manager.request_async()
        result=[]
        for session in manager.get_sessions():
            playback=session.get_playback_info()
            if playback.playback_status!=Status.PLAYING:continue
            properties=await session.try_get_media_properties_async()
            if properties is None:continue
            kind=properties.playback_type or playback.playback_type
            result.append({'app_id':session.source_app_user_model_id,'title':properties.title[:250],
                           'video':kind==MediaPlaybackType.VIDEO,'music':kind==MediaPlaybackType.MUSIC})
        return result

def match_playback(windows,sessions):
    detected=[dict(w,reason='game-window' if w.get('game') else 'fullscreen-app') for w in windows if w['fullscreen'] or w.get('game')]
    for session in sessions:
        app=session['app_id'].lower()
        title=session['title'].casefold()
        candidates=[]
        for window in windows:
            stem=PureWindowsPath(window['app']).stem.lower()
            label=window['title'].casefold()
            app_match=bool(stem and (stem in app or ('netflix' in app and 'netflix' in label)))
            title_match=bool(len(title)>=4 and (title in label or label in title))
            if app_match or title_match:candidates.append((window,title_match))
        exact=[w for w,matched in candidates if matched]
        selected=exact or [w for w,_ in candidates]
        for window in selected:
            # Unknown playback type is accepted for browser video/media titles.
            video_hint=any(word in (window['title']+' '+session['title']).lower() for word in ('youtube','netflix','twitch','prime video','disney','video'))
            browser=window['app'] in ('chrome.exe','msedge.exe','firefox.exe','brave.exe','opera.exe')
            if session['video'] or video_hint or browser:
                detected.append(dict(window,reason='playing-media',media_title=session['title']))
    return detected

def scan_media():
    windows=windows_snapshot()
    try:
        sessions=asyncio.run(playback_snapshot())
        error=''
    except Exception as exc:
        sessions=[];error=type(exc).__name__
    return {'detected':match_playback(windows,sessions),'session_count':len(sessions),'error':error}
