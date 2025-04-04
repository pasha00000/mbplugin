# -*- coding: utf8 -*-
''' Автор ArtyLa
для того чтобы не писать утилиты два раза для windows и linux все переносим сюда, а
непосредственно в bat и sh скриптах оставляем вызов этого скрипта
'''
import os, sys, platform, re, time, subprocess, shutil, glob, pathlib, logging, pprint, importlib, zipfile
import click

# Т.к. мы меняем текущую папку, то sys.argv[0] будет смотреть не туда, пользоваться можно только
# папка где плагины
CRLF = '\n'
PLUGIN_PATH = os.path.abspath(os.path.split(__file__)[0])
# Папка корня standalone версии на 2 уровня вверх (оно же settings.mbplugin_root_path)
ROOT_PATH = os.path.abspath(os.path.join(PLUGIN_PATH, '..', '..'))
# Для пути с симлинками в unix-like системах приходится идти на трюки (см комментарий в store.switch_to_mb_mode):
if sys.platform != 'win32' and 'PWD' in os.environ:
    if os.path.exists(os.path.abspath(os.path.join(os.environ['PWD'], 'mbplugin', 'plugin', 'util.py'))):
        ROOT_PATH = os.environ['PWD']
STANDALONE_PATH = ROOT_PATH
# папка где embedded python (только в windows)
EMB_PYTHON_PATH = os.path.abspath(os.path.join(PLUGIN_PATH, os.path.join('..', 'python')))
SYS_PATH_ORIGIN = sys.path[:]  # Оригинальное значение sys.path
try:
    import store, settings
except ModuleNotFoundError:
    click.echo(f'Not found plugin folder use\n  {sys.argv[0]} fix-embedded-python-path')
    sys.path.insert(0, PLUGIN_PATH)
    import store, settings

def echo(msg: str):
    'Обертка, для click.echo чтобы можно было завернуть запись в файл диагностики параллельно с выводом на экран'
    click.echo(msg)
    if os.environ.get('MBPLUGIN_WRITE_DIAG'):
        path = store.abspath_join('mbplugin', 'log', 'setup_diag.txt')
        with open(path, 'a') as f:
            f.write(f"{time.strftime('%d.%m.%Y %H:%M:%S', time.localtime())} {msg}\n")

@click.group()
@click.option('-d', '--debug', is_flag=True, help='Debug mode')
@click.option('-v', '--verbose', is_flag=True, help='Verbose mode')
@click.pass_context
def cli(ctx, debug, verbose):
    ctx.ensure_object(dict)
    ctx.obj['DEBUG'] = debug
    ctx.obj['VERBOSE'] = verbose


@cli.command()
@click.argument('expression', type=str, nargs=-1)
@click.pass_context
def set(ctx, expression):
    '''Установка/сброс опции, для флагов используйте 1/0
    Включить показ хрома при работе:
    mbp set ini/Options/show_chrome=1 \b
    если в качестве значения указан default происходит сброс к установкам по умолчанию
    для установки  \b mbp set ini/HttpServer/start_http=1
    или для сброса \b mbp set ini/HttpServer/start_http=default
    '''
    name = 'set'
    import settings
    expression_prep = '='.join(expression)
    mbplugin_ini = store.ini()
    mbplugin_ini.read()
    if not re.match(r'^\w+/\w+/\w+=\S+$', expression_prep):
        echo(f'Non valid expression {expression_prep}')
        return
    path, value = expression_prep.split('=')
    _, section, key = path.split('/')
    if section not in settings.ini:
        echo(f'Warning: Non-existent section {section}')
    if key not in settings.ini.get(section, {}):
        echo(f'Warning: Non-existent key {key} in section {section}')
    if value.lower() == 'default' and key in mbplugin_ini.ini[section]:
        del mbplugin_ini.ini[section][key]
    else:
        mbplugin_ini.ini[section][key] = value
    mbplugin_ini.write()
    echo(f'Set {path} -> {value}')


@cli.command()
@click.pass_context
def fix_embedded_python_path(ctx):
    '''
    Исправляем пути embedded python
    добавляем в sys.path поиск в папке откуда запущен скрипт по умолчанию, в embedded он почему-то выключен
    Только если папка с python есть добавляем в sitecustomize.py путь к текущей папке'''
    name = 'fix_embedded_python_path'
    if PLUGIN_PATH not in SYS_PATH_ORIGIN:
        try:
            echo(f'Add current path to sys.path by default')
            txt = '\nimport os, sys\nsys.path.insert(0,os.path.abspath(os.path.abspath(os.path.dirname(__file__))))\n'
            if os.path.isdir(EMB_PYTHON_PATH):
                open(os.path.join(EMB_PYTHON_PATH, 'sitecustomize.py'), 'a').write(txt)
            echo(f'OK {name}')
        except Exception:
            echo(f'Fail {name}: {store.exception_text()}')
            sys.exit(1)
    else:
        echo(f'Not needed {name}')


@cli.command()
@click.argument('browsers', nargs=-1)
@click.pass_context
def install_chromium(ctx, browsers):
    '''Устанавливаем движок chromium, только если включена опция use_builtin_browser, по умолчанию ставим только тот движок, который прописан в ini'''
    name = 'install-chromium'
    store.turn_logging()
    if str(store.options('use_builtin_browser')) != '1':
        echo(f'Not needed {name}')
        return
    try:
        if len(browsers) == 0:
            subprocess.check_call([sys.executable, '-m', 'playwright', 'install', store.options('browsertype')])  # '--with-deps', ???
            echo(f"OK {name} {store.options('browsertype')}")
        else:
            subprocess.check_call([sys.executable, '-m', 'playwright', 'install', *browsers])  # '--with-deps', ???
            echo(f"OK {name} {','.join(browsers)}")
    except Exception:
        echo(f'Fail {name}: {store.exception_text()}')
        sys.exit(1)


@cli.command()
@click.option('-q', '--quiet', is_flag=True)
@click.option('-c', '--check-only', is_flag=True)
@click.pass_context
def pip_update(ctx, quiet, check_only):
    '''Проверяем или обновляем пакеты по requirements.txt или requirements_win.txt или requirements_win7.txt'''
    name = 'pip-update'
    flags = " -q " if quiet else ""
    if store.options('requirements').strip() != '':
        requirements_path = os.path.join(ROOT_PATH, 'mbplugin', 'docker', store.options('requirements').strip())
    elif sys.platform == 'win32':
        #if int(platform.version().split('.')[0]) >= 10: # win10
        requirements_path = os.path.join(ROOT_PATH, 'mbplugin', 'docker', 'requirements_win.txt')
        #else:
        #    requirements_path = os.path.join(ROOT_PATH, 'mbplugin', 'docker', 'requirements_win7.txt')
        flags += ' --no-warn-script-location '
    else:
        requirements_path = os.path.join(ROOT_PATH, 'mbplugin', 'docker', 'requirements.txt')
    if check_only:
        freeze = {line.strip() for line in os.popen(f'"{sys.executable}" -m pip freeze').readlines() if '==' in line}
        freeze_pack = {line.split('==')[0] for line in freeze}
        requirements = {line.strip() for line in open(requirements_path).readlines() if '==' in line}
        requirements_pack = {line.split('==')[0] for line in requirements}
        not_installed = requirements_pack.difference(freeze_pack)
        not_same_version = requirements.difference(freeze)
        if len(not_installed) > 0:
            echo(f'Fail {name}: Not all packages are installed: {",".join(not_installed)}')
            sys.exit(1)
        if len(not_same_version) > 0:
            echo(f'Fail {name}: Not all packages are installed with the correct version: {",".join(not_same_version)}')
            sys.exit(2)
        echo(f'OK {name}')
        return
    os.system(f'"{sys.executable}" -m pip install {flags} --upgrade pip wheel setuptools')
    os.system(f'"{sys.executable}" -m pip install {flags} -r {requirements_path}')
    echo(f'OK {name}')


@cli.command()
@click.option('--soft', is_flag=True, help='Мягкая очистка, освободить место, но сохранить сессии, по умолчанию полная очистка со сбросом сессий')
@click.pass_context
def clear_browser_cache(ctx, soft):
    '''Очищаем кэш браузера'''
    name = 'clear_browser_cache'
    try:
        if soft:
            path = pathlib.Path(ROOT_PATH, 'mbplugin', 'store', 'headless')
            [(shutil.rmtree(fl) if fl.is_dir() else fl.unlink()) for fl in path.rglob('*') if 'Cache' in fl.name or fl.name.startswith('BrowserMetrics') or fl.name in ['History', 'Favicons', 'Visited Links', 'component_crx_cache', 'ClientSidePhishing', 'hyphen-data']]
        else:
            [os.remove(fn) for fn in glob.glob(os.path.join(ROOT_PATH, 'mbplugin', 'store', 'p_*'))]
            shutil.rmtree(os.path.join(ROOT_PATH, 'mbplugin', 'store', 'puppeteer'), ignore_errors=True)
            shutil.rmtree(os.path.join(ROOT_PATH, 'mbplugin', 'store', 'headless'), ignore_errors=True)
        echo(f'OK {name}')
    except Exception:
        echo(f'Fail {name}: {store.exception_text()}')
        sys.exit(1)


@cli.command()
@click.option('--skip-dll', is_flag=True, help='Пропустить сборку DLL')
@click.option('--skip-jsmblh', is_flag=True, help='Пропустить сборку JSMB LH')
@click.option('--prepare-link', is_flag=True, help='Подготовить линки на ЛК операторов')
@click.pass_context
def recompile_plugin(ctx, skip_dll, skip_jsmblh, prepare_link):
    'Пересобираем DLL и JSMB LH плагины (только windows) все равно MobileBalance только под windows работает'
    name = 'recompile-plugin'
    if prepare_link:
        links = {}
        for fn in glob.glob('mbplugin\\plugin\\*.py'):
            pluginname = f'p_{os.path.splitext(os.path.split(fn)[1])[0]}'
            compile_bat = os.path.join(ROOT_PATH, 'mbplugin', 'dllsource', 'compile.bat')
            body = open(fn, encoding='utf8').read()
            if 'def' + ' get_balance(' in body and 'login_url = ' in body:
                matches = re.findall(r"(?usi)login_url = '(.*?)'", body)
                if len(matches) > 0:
                    links[pluginname] = matches[0]
        click.echo(pprint.PrettyPrinter(indent=4, width=160).pformat(links))
    if sys.platform == 'win32':
        if not skip_dll:  # Пересобираем DLL plugin
            try:
                # os.system(f"{os.path.join(ROOT_PATH, 'mbplugin', 'dllsource', 'compile_all_p.bat')}")
                for fn in glob.glob('mbplugin\\plugin\\*.py'):
                    pluginname = f'p_{os.path.splitext(os.path.split(fn)[1])[0]}'
                    src = os.path.join(ROOT_PATH, 'mbplugin', 'dllsource', pluginname + '.dll')
                    dst = os.path.join(ROOT_PATH, 'mbplugin', 'dllplugin', pluginname + '.dll')
                    compile_bat = os.path.join(ROOT_PATH, 'mbplugin', 'dllsource', 'compile.bat')
                    if 'def' + ' get_balance(' in open(fn, encoding='utf8').read():
                        os.system(f'{compile_bat} {pluginname}')
                        shutil.move(src, dst)
                    if ctx.obj['VERBOSE']:
                        echo(f'Move {pluginname}.dll -> dllplugin\\')
                echo(f'OK {name} DLL')
            except Exception:
                echo(f'Fail {name}: {store.exception_text()}')
        if not skip_jsmblh:  # Пересобираем JSMB LH plugin
            import compile_all_jsmblh
            try:
                compile_all_jsmblh.recompile(PLUGIN_PATH, verbose=ctx.obj['VERBOSE'])
                echo(f'OK {name} jsmblh')
            except Exception:
                echo(f'Fail {name}: {store.exception_text()}')
                sys.exit(1)
    else:
        echo('On windows platform only')


@cli.command()
@click.pass_context
def check_import(ctx):
    'Проверяем что все модули импортируются'
    name = 'check-import'
    try:
        # python -m pip install --upgrade pip wheel setuptools
        # python -m pip install urllib3==1.26.18 click requests pyTelegramBotAPI rich playwright==1.14.1 Pillow==9.5.0 beautifulsoup4 pyreadline3 psutil schedule pywin32 pyodbc pystray playwright_stealth websocket-client cryptography
        import telebot, requests, PIL, bs4, readline, psutil, playwright, playwright_stealth, schedule, rich, websocket, cryptography
        if sys.platform == 'win32':
            import win32api, win32gui, win32con, pyodbc, pystray
    except ModuleNotFoundError:
        echo(f'Fail {name}: {store.exception_text()}')
        sys.exit(1)
    echo(f'OK {name}')


@cli.command()
@click.pass_context
def web_control(ctx):
    'Открываем страницу управления mbplugin (если запущен веб-сервер)'
    name = 'web-control'
    os.system(f'{store.start_cmd()} http://localhost:{store.options("port", section="HttpServer")}/main')
    echo(f'OK {name}')


@cli.command()
@click.argument('turn', type=click.Choice(['on', 'off'], case_sensitive=False), default='on')
@click.pass_context
def web_server_autostart(ctx, turn):
    '''Автозапуск web сервера (только windows) и только если разрешен в ini
    on - Создаем lnk на run_webserver.bat и помещаем его в автозапуск и запускаем
    off - убираем из авто запуска
    для отключения в ini дайте команду mbp set ini\\HttpServer\\start_http=0
    '''
    name = 'web-server-autostart'
    if sys.platform == 'win32':
        try:
            import win32com.client
            shell = win32com.client.Dispatch('WScript.Shell')
            lnk_path = os.path.join(ROOT_PATH, 'mbplugin', 'run_webserver.lnk')
            lnk_startup_path = f"{os.environ['APPDATA']}\\Microsoft\\Windows\\Start Menu\\Programs\\Startup"
            lnk_startup_full_name = f"{os.environ['APPDATA']}\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\run_webserver.lnk"
            shortcut = shell.CreateShortCut(lnk_path)
            shortcut.Targetpath = os.path.join(ROOT_PATH, 'mbplugin', 'run_webserver.bat')
            shortcut.save()
            start_http = str(store.options('start_http', section='HttpServer'))
            autostart_http = str(store.options('autostart_http', section='HttpServer'))
            if turn == 'on' and start_http == '1' and autostart_http == '1':
                # %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
                shutil.copy(lnk_path, lnk_startup_path)
                os.system(f'"{lnk_startup_full_name}"')
            else:  # if turn == 'off':
                if not (start_http == '1' and autostart_http == '1'):
                    echo(f'Start http server disabled in mbplugin.ini ({start_http=}, {autostart_http=})')
                if os.path.exists(lnk_startup_full_name):
                    os.remove(lnk_startup_full_name)
            time.sleep(4)
            echo(f'OK {name} {turn}')
        except Exception:
            echo(f'Fail {name}: {store.exception_text()}')
            sys.exit(1)
    else:
        echo('On windows platform only')


@cli.command()
@click.argument('cmd', type=click.Choice(['start', 'stop', 'restart'], case_sensitive=False))
@click.option('-f', '--force', is_flag=True, help='Force kill')
@click.pass_context
def web_server(ctx, cmd, force):
    'start/stop/restart web сервер'
    name = 'web-server'
    import httpserver_mobile
    try:
        if cmd == 'stop' or cmd == 'restart':
            httpserver_mobile.send_http_signal('exit', force=force)
        if cmd == 'start' or cmd == 'restart':
            if sys.platform == 'win32':
                lnk_path = os.path.join(ROOT_PATH, 'mbplugin', 'run_webserver.bat')
                os.system(f'"{lnk_path}"')
            else:
                httpserver_mobile.WebServer()
        time.sleep(3)
        echo(f'OK {name} {cmd}')
    except Exception:
        echo(f'Fail {name}: {store.exception_text()}')
        sys.exit(1)


@cli.command()
@click.pass_context
def reload_schedule(ctx):
    'Перечитывает расписание запросов баланса'
    name = 'reload-schedule'
    import httpserver_mobile
    res = httpserver_mobile.send_http_signal(cmd='reload_schedule')
    echo(f'OK {name}\n{res}')


@cli.command()
@click.argument('plugin', type=click.Choice(['simple', 'chrome'], case_sensitive=False), default='simple')
@click.pass_context
def check_jsmblh(ctx, plugin):
    'Проверяем что все работает JSMB LH PLUGIN простой плагин'
    name = 'check_jsmblh'
    if str(store.options('start_http', section='HttpServer')) != '1':
        echo(f'Start http server disabled in mbplugin.ini (start_http=0)')
        return
    import re, requests
    # Здесь не важно какой плагин мы берем, нам нужен только адрес с портом, а он у всех одинаковый
    # Можно было бы взять из ini, но мы заодно проверяем что в плагинах правильный url
    path = os.path.join(ROOT_PATH, 'mbplugin', 'jsmblhplugin', 'p_test1_localweb.jsmb')
    url = re.findall(r'(?usi)(http://127.0.0.1:.*?/)', open(path).read())[0]
    try:
        if plugin == 'simple':
            res = requests.session().get(url + f'getbalance/p_test1/123/456/789').content.decode('cp1251')
        else:
            res = requests.session().get(url + 'getbalance/p_test3/demo@saures.ru/demo/789').content.decode('cp1251')
        echo(f'OK {name} {plugin}')
        if ctx.obj['VERBOSE']:
            echo(f'{res}')
    except Exception:
        echo(f'Fail {name} {plugin}:\n{store.exception_text()}')
        sys.exit(1)


@cli.command()
@click.pass_context
def check_dll(ctx):
    'Проверяем что все работает DLL PLUGIN'
    name = 'check-dll'
    # call plugin\test_mbplugin_dll_call.bat p_test1 123 456
    if sys.platform == 'win32':
        try:
            import dll_call_test
            # echo INFO:
            res = dll_call_test.dll_call('p_test1', 'Info', '123', '456')
            if ctx.obj['VERBOSE']:
                echo(f'Info:{res}')
            # echo EXECUTE:
            res = dll_call_test.dll_call('p_test1', 'Execute', '123', '456')
            if ctx.obj['VERBOSE']:
                echo(f'Execute:{res}')
            echo(f'OK {name}')
        except Exception:
            echo(f'Fail {name}:\n{store.exception_text()}')
            sys.exit(1)
    else:
        echo('On windows platform only')


@cli.command()
@click.pass_context
def check_playwright(ctx):
    'Проверяем что playwright работает'
    name = 'check-playwright'
    store.turn_logging()
    import browsercontroller
    browser = browsercontroller.BrowserController(login='', password='', storename='test', plugin_name=__name__)
    result = browser.main(run=browsercontroller.CHECK_PLAYWRIGHT)
    if hasattr(browser.main, '__exception_text__'):
        echo(f'Fail {name}:\n{browser.main.__exception_text__}')
        sys.exit(1)
    elif 'Balance' not in result:
        echo(f'Fail {name}:\nno result')
        sys.exit(2)
    elif result['Balance'] > 0:
        echo(f'OK {name} {result["Balance"]}')
    else:
        echo(f'Fail {name}:\nresult=0')
        sys.exit(3)


@cli.command()
@click.pass_context
def init(ctx):
    '''Инициализация можно втором параметром указать noweb тогда веб сервер не будет запускаться и помещаться в автозапуск
    Если в mbplugin.ini пути не правильные то прописывает абсолютные пути к тем файлам, которые лежат в текущей папке
    копирует phones.ini из примера, если его еще нет
    '''
    name = 'init'
    try:
        if not os.path.exists(store.abspath_join(store.settings.mbplugin_ini_path, 'phones.ini')):
            echo(f'The folder {store.settings.mbplugin_ini_path} must contain a file phones.ini, copy example')
            shutil.copy(store.abspath_join(store.settings.mbplugin_root_path, 'mbplugin', 'standalone', 'phones.ini'),
                        store.abspath_join(store.settings.mbplugin_ini_path, 'phones.ini'))
        ini = store.ini()
        ini.read()
        # TODO пока для совместимости НЕ Убираем устаревшую секцию MobileBalance - она больше не используется
        # ini.ini.remove_section('MobileBalance')
        # Если лежит mobilebalance - отрабатываем обычный, а не автономный конфиг
        if not os.path.exists(store.abspath_join(store.settings.mbplugin_ini_path, 'MobileBalance.exe')):
            # echo(f'The folder {STANDALONE_PATH} must not contain a file mobilebalance.exe')
            # Запись SQLITE, создание report и работу с phone.ini из скриптов точно включаем если рядом нет mobilebalance.exe, иначе это остается на выбор пользователя
            ini.ini['Options']['sqlitestore'] = '1'
            ini.ini['Options']['createhtmlreport'] = '1'
            ini.ini['Options']['phone_ini_save'] = '1'
        # TODO пока для совместимости ini со старой версией оставляем путь как есть если если он абсолютный и файл по нему есть
        if not (os.path.abspath(ini.ini['Options']['balance_html']) == os.path.abspath('balance.html') and os.path.exists(ini.ini['Options']['balance_html'])):
            ini.ini['Options']['balance_html'] = 'balance.html'
        ini.write()
        echo(f'OK {name}')
    except Exception:
        echo(f'Fail {name}:\n{store.exception_text()}')
        sys.exit(1)


@cli.command(name='get-balance')
@click.option('--only_failed', is_flag=True, help='Запросить балансы, по которым были ошибки')
@click.argument('filter', nargs=-1)
@click.pass_context
def full_get_balance(ctx, only_failed, filter):  # !!! нельзя пользоваться именем get_balance т.к. по нему фильтруются тесты и построители плагинов
    'Получение балансов, можно указать only_failed, тогда будут запрошены только те где последняя попытка была неудачной'
    name = 'get-balance'
    store.turn_logging()
    import httpserver_mobile
    # breakpoint()
    result = httpserver_mobile.getbalance_standalone(filter_tel=filter, only_failed=only_failed)
    for k, v in result.items():
        echo(f"{k} {'OK' if v else 'BAD'}")
    state = 'ALL_OK' if all(result.values()) else 'ANY_OK' if any(result.values()) else 'NOONE_OK'
    state_code = 0 if all(result.values()) else 1 if any(result.values()) else 2
    counters = f'OK:{list(result.values()).count(True)}/BAD:{list(result.values()).count(False)}/ALL:{len(result)}'
    echo(f'{name} {state} {counters}')
    sys.exit(state_code)


@cli.command()
@click.pass_context
def refresh_balance_html(ctx):
    'Обновить balance.html'
    name = 'refresh-balance-html'
    store.turn_logging()
    try:
        import httpserver_mobile
        httpserver_mobile.write_report()
        echo(f'OK {name}')
    except Exception as e:
        echo(f'Fail {name}:\n{store.exception_text()}')
        sys.exit(1)

@cli.command()
@click.argument('path', type=str, default='')
@click.pass_context
def copy_all_from_other_db(ctx, path):
    'копировать все данные из бд sqlite или mbd, по дефолту берем базу mdb в той же папке где и база'
    name = 'copy-all-from-other-db'
    import dbengine
    if path == '':
        path = store.abspath_join(store.settings.mbplugin_ini_path, 'BalanceHistory.mdb')
    echo(f'Update from {path} ...')
    ext = os.path.splitext(path)[1].lower()
    if ext == '.mdb':  # копировать все данные из mdb
        if store.options('updatefrommdb') != '1':
            echo(f'Fail {name}\n:updatefrommdb turn in OFF')
            sys.exit(1)
        store.turn_logging(logginglevel=logging.DEBUG)
        if not dbengine.update_sqlite_from_mdb(dbname=path, deep=10000):
            echo(f'Fail {name} from {path}\nsee log')
            sys.exit(2)
    elif ext == '.sqlite':  # копировать все данные из sqlite
        store.turn_logging(logginglevel=logging.DEBUG)
        if not dbengine.Dbengine().copy_data(path):
            echo(f'Fail {name} from {path}\nsee log')
            sys.exit(3)
    else:
        echo(f'Fail {name}\nUnknown type {ext}')
        sys.exit(4)
    echo(f'OK {name}')

@cli.command()
@click.option('-r', '--over_requests', is_flag=True, help='Отправка баланса TG чистым requests без использования web сервера')
@click.pass_context
def send_tgbalance(ctx, over_requests):
    'Отправка баланса TG через API веб-сервера'
    name = 'send-tgbalance'
    import httpserver_mobile
    if over_requests:
        httpserver_mobile.send_telegram_over_requests()
        echo(f'OK {name}')
    else:
        # Sendtgbalance
        res1 = httpserver_mobile.send_http_signal(cmd='sendtgbalance')
        # Subscription
        res2 = httpserver_mobile.send_http_signal(cmd='sendtgsubscriptions')
        echo(f'OK {name}\nSendtgbalance: {res1}\nSubscription: {res2}')


@cli.command()
@click.argument('action', type=click.Choice(['hide', 'show'], case_sensitive=False), default='hide')
@click.pass_context
def show_chrome(ctx, action):
    'Показывает спрятанный chrome. Работает только на windows, и только при headless_chrome = 0, если chrome запущен в режиме headless то его показать нельзя'
    name = 'show-chrome'
    store.turn_logging()
    import browsercontroller
    if sys.platform == 'win32':
        browsercontroller.hide_chrome(hide=(action == 'hide'))
        echo(f'OK {name}')
    else:
        echo(f'{name}:On windows platform only')

def do_check_ini():
    '''Проверяет ini файлы и возвращает 
    mbplugin_ini_ok - bool
    mbplugin_ini_mess - подробное описание по phones.ini
    phones_ini_ok - bool
    phones_ini_mess - подробное описание по phones.ini + phones_add.ini'''
    import httpserver_mobile
    mbplugin_ini = store.ini()
    mbplugin_ini.read()
    mbplugin_ini_mess = []
    mbplugin_ini_ok = True
    if 'Telegram' in mbplugin_ini.ini:
        if len([i for i in mbplugin_ini.ini['Telegram'].keys() if i.startswith('subscrib' + 'tion')]):
            msg = f'Warning check-ini mbplugin.ini - subsri_B_tion key found in ini'
            mbplugin_ini_mess.append(msg)
            mbplugin_ini_ok = False
    for sec in store.settings.ini.keys():
        for key in store.settings.ini[sec]:
            if not key.endswith('_'):
                valid, msg = store.option_validate(key, section=sec)
                if not valid:
                    mbplugin_ini_mess.append(f'Section [{sec}]: ' + msg)
                    mbplugin_ini_ok = False
    jobs = httpserver_mobile.Scheduler(check_only=True).read_from_ini()
    mbplugin_ini_mess.extend([f'{job.err_msg}\n{job.job_str}' for job in jobs if job.err_msg != ''])
    # echo(f'{mbplugin_ini_status} {name} mbplugin.ini {CRLF + CRLF.join(mbplugin_ini_mess)}'.strip())
    phones_ini_mess = []
    phones_ini_ok = True
    phones_ini = store.ini('phones.ini')
    phones_ini.read()
    for nn in phones_ini.ini.keys():
        if nn == 'DEFAULT':
            continue
        if not nn.isdigit():
            phones_ini_mess.append(f'Invalid section number [{nn}]')
            phones_ini_ok = False
            continue
        if phones_ini.ini[nn].get('monitor', 'false').lower() != 'true':
            phones_ini_mess.append(f'Section [{nn}] is not Monitor = TRUE, skip')
            continue
        try:
            pkey = store.get_pkey(phones_ini.ini[nn]['number'], phones_ini.ini[nn]['region'])
            for key in phones_ini.ini[nn].keys():
                valid, msg = store.option_validate(key, pkey=pkey)
                if not valid:
                    phones_ini_mess.append(f'Section [Phone] #{nn} ' + msg)
                    phones_ini_ok = False
                if key.lower() not in store.settings.ini['Options'] and key.lower() not in store.settings.PHONE_INI_KEYS_LOWER and key.lower() not in ('phone_orig', 'number_orig', 'region_orig'):
                    phones_ini_mess.append(f'Section [Phone] #{nn} has unused {key}')
                    phones_ini_ok = False
        except Exception:
            phones_ini_ok = False
            phones_ini_mess.append(f'Check phones phones.ini/phones_add.ini generate error:\n{store.exception_text()}')
            break
    #echo(f'{phones_ini_status} {name} phones.ini {CRLF +  CRLF.join(phones_ini_mess)}'.strip())
    return [mbplugin_ini_ok, mbplugin_ini_mess, phones_ini_ok, phones_ini_mess]

@cli.command()
@click.pass_context
def check_ini(ctx):
    'Проверка INI на корректность'
    name = 'check-ini'
    try:
        mbplugin_ini_ok, mbplugin_ini_mess, phones_ini_ok, phones_ini_mess = do_check_ini()
        mbplugin_ini_status = 'OK' if mbplugin_ini_ok else 'Fail'
        phones_ini_status = 'OK' if phones_ini_ok else 'Fail'
        echo(f'{mbplugin_ini_status} {name} mbplugin.ini {CRLF + CRLF.join(mbplugin_ini_mess)}'.strip())
        echo(f'{phones_ini_status} {name} phones.ini {CRLF +  CRLF.join(phones_ini_mess)}'.strip())
    except Exception:
        echo(f'Fail {name}:\n{store.exception_text()}')
        sys.exit(1)


@cli.command()
@click.option('-b', '--bpoint', type=int)
@click.option('-p', '--params', multiple=True, type=click.Tuple([str, str]), help='override parameters ex. -p showchrome 1 -p plugin_mode WEB')
@click.argument('plugin', type=str)
@click.argument('login', type=str)
@click.argument('password', type=str)
@click.pass_context
def check_plugin(ctx, bpoint, params, plugin, login, password):
    'Проверка работы плагина по заданному логину и паролю'
    name = 'check-plugin'
    store.options('', mainparams=dict(params))  # Надо давать до turn_logging т.к. там могут быть настройки которые повлияют на логинг, например logconsole=1
    store.turn_logging()
    logging.info(f'mainparams={dict(params)}')
    echo(f'{plugin} {login} {password}')
    import httpserver_mobile
    if bpoint:
        import pdb
        pdbpdb = pdb.Pdb()  # pylint: disable=no-member
        lang = 'p'
        plugin = plugin.split('_', 1)[1]  # plugin это все что после p_
        module = __import__(plugin, globals(), locals(), [], 0)
        importlib.reload(module)  # обновляем модуль, на случай если он менялся
        storename = store.gen_storename(plugin, login)
        pdbpdb.set_break(module.__file__, bpoint)
        # module.get_balance(login,  password, storename)
        _ = login, password, storename  # dummy linter - use in pdbpdb.run
        result = pdbpdb.run("module.get_balance(login,  password, storename)", globals(), locals())
        pkey = store.get_pkey(login, plugin)
        result = store.correct_and_check_result(result, pkey)
        # res = exec("httpserver_mobile.getbalance_plugin('url', [plugin, login, password, '123'])", globals(), locals())
        # breakpoint()
    else:
        result = httpserver_mobile.getbalance_plugin('url', [plugin, login, password, '123'])
    echo(f'{name}:\n{result}')
    sys.exit(0 if 'Balance' in repr(result) else 1)


@cli.command()
@click.pass_context
def phone_list(ctx):
    'Выдает список номеров телефонов из phones.ini'
    name = 'phone-list'
    phones = store.ini('phones.ini')
    phones.read()
    for sec in phones.ini.sections():
        if phones.ini[sec].get('Monitor', 'FALSE') == 'TRUE':
            echo(f'{sec:3} {phones.ini[sec]["Alias"]:20} {phones.ini[sec]["Region"]:20} {phones.ini[sec]["Number"]:20}')
    echo(f'OK {name}')


@cli.command()
@click.option('-n', '--num', type=int, default=-1)
@click.option('-d', '--delete', is_flag=True)
@click.option('-pl', '--plugin', type=str, default='')
@click.option('-m', '--monitor', type=click.Choice(['true', 'false', ''], case_sensitive=False), default='')
@click.option('-a', '--alias', type=str, default='')
@click.option('-l', '--login', type=str, default='')
@click.option('-p', '--password', type=str, default='')
@click.pass_context
def phone_change(ctx, num, delete, plugin, monitor, alias, login, password):
    'Добавить или изменить или удалить номер в phones.ini'
    name = 'phone-change'
    store.turn_logging()
    if str(store.options('phone_ini_save')) == '0':
        echo('Work with phone.ini from mbp not allowed (turn phone_ini_save=1 in mbplugin.ini)')
        return
    cmd = "DELETE" if delete else ("CHANGE" if num > 0 else "CREATE")
    echo(f'{cmd}')
    echo(f'num:{num} alias:{alias}, plugin:{plugin}, monitor:{monitor}, login:{login}, password:{password}')
    phones = store.ini('phones.ini')
    phones.read()
    if delete:
        if str(num) in phones.ini.sections():
            echo(f'Delete {list(phones.ini[str(num)].items())}')
            del phones.ini[str(num)]
        else:
            for sec in phones.ini.sections():
                if ((phones.ini[sec]['Region'] == plugin or plugin == '') and (phones.ini[sec]['Number'] == login or login == '') and (phones.ini[sec]['Alias'] == alias or alias == '')):
                    echo(f'Delete {list(phones.ini[sec].items())}')
                    del phones.ini[sec]
    if not delete and num < 0:
        if plugin == '' or login == '' or password == '':
            echo('For new phone plugin login and password must be specified')
            return
        exists = [sec for sec in phones.ini.sections()
                  if phones.ini[sec]['Region'] == plugin and phones.ini[sec]['Number'] == login]
        if len(exists) > 0:
            echo(f'Already exists {exists[0]} {phones.ini[exists[0]]}')
            return
        sec = str(max([int(i) for i in phones.ini.sections()]) + 1)
        phones.ini[sec] = {
            'Region': plugin,
            'Monitor': str(monitor != 'false').upper(),
            'Alias': (login if alias == '' else alias),
            'Number': login,
            'Password2': password
        }
        echo(f'Create {list(phones.ini[sec].items())}')
    if not delete and str(num) in phones.ini.sections():
        if plugin != '':
            phones.ini[str(num)]['Region'] = plugin
        if monitor != '':
            phones.ini[str(num)]['Monitor'] = monitor.upper()
        if alias != '':
            phones.ini[str(num)]['Alias'] = alias
        if login != '':
            phones.ini[str(num)]['Number'] = login
        if password != '':
            phones.ini[str(num)]['Password2'] = password
        echo(f'Change {list(phones.ini[str(num)].items())}')
    phones.write()
    echo(f'OK {name} {cmd}')


@cli.command()
@click.option('-v', '--verbose', is_flag=True, help='Показать версии пакетов и хрома')
@click.option('-d', '--download-stat', is_flag=True, help='Показать статистику по загрузкам разных версий')
@click.pass_context
def version(ctx, verbose, download_stat):
    'Текущая установленная версия'
    name = 'version'
    store.turn_logging()
    if download_stat or verbose:
        import updateengine
        updater = updateengine.UpdaterEngine()
    if download_stat:
        echo(updater.download_statistics())
    echo(f'Mbplugin version {store.version()}')
    if not verbose:
        return
    echo(f'Python {sys.version}')
    import playwright._repo_version, playwright.sync_api, requests
    echo(f'Playwright {playwright._repo_version.version}')
    import browsercontroller
    browser = browsercontroller.BrowserController(login='', password='', storename='test', plugin_name=__name__)
    result = browser.main(run=browsercontroller.CHECK_PLAYWRIGHT)
    echo(result.get('Version'))  # chromium Mozilla ...
    if updater.check_update():
        version, msg_version = updater.latest_version_info()
        echo(f'New version found {version}\n{msg_version}')
    else:
        version, msg_version = updater.latest_version_info(short=True)
        echo(f'No new version found on github release, latest version:{version}\n{msg_version}')
        return


@cli.command()
@click.option('-f', '--force', is_flag=True, help='С заменой измененных файлов')
@click.option('-v', '--version', type=str, default='', help='Указать конкретный номер версии (по тэгу) или имени файла')
@click.option('--only-download', is_flag=True, help='Только загрузить')
@click.option('--only-check', is_flag=True, help='Только проверить')
@click.option('--only-install', is_flag=True, help='Только установить новую (должна быть скачана заранее)')
@click.option('--by-current', is_flag=True, help='Обновить файлы по архиву текущей версии')
@click.option('--undo-update', is_flag=True, help='Вернуть файлы к варианту до обновления')
@click.option('--ask-update', is_flag=True, help='Выдать запрос на обновление')
@click.option('--no-check-sign', is_flag=True, help='Не проверять подпись файла с версией при загрузке')
@click.option('--no-verify-ssl', is_flag=True, help='Отключить проверку SSL')
@click.option('--install-prerelease', is_flag=True, help='Устанавливать бета-версии')
@click.option('--batch_mode', is_flag=True, help='Игнорировать ключи, брать параметры из mbplugin.ini')
@click.pass_context
def version_update(ctx, force, version, only_download, only_check, only_install, by_current, undo_update, ask_update, no_check_sign, no_verify_ssl, install_prerelease, batch_mode):
    '''Загружает и обновляет файлы из pack с новой версией, архив с новой версией при обновлении копируем в current.zip
    version=='' - обновляем до последней, если указана как имя zip файла из папки pack если указана как номер версии по тэгу качаем с github'''
    name = 'version-update'
    if batch_mode:
        # Если это batch режим и не включен autoupdate то сразу выходим
        if str(store.options('autoupdate')) == '0':
            return
        ask_update = str(store.options('ask_update')) == '1'
    skip_download = only_check or only_install or by_current or undo_update and not only_download
    skip_install = only_check or only_download and not only_install and not by_current and not undo_update
    echo(f'Current version {store.version()}')
    res, msg = True, ''
    import updateengine
    updater = updateengine.UpdaterEngine(version=version, prerelease=install_prerelease, verify_ssl=not no_verify_ssl)
    if sum([only_download, only_check, only_install, by_current, undo_update]) > 1:
        echo(f'Only one option can be used')
        return
    if version == '' and not by_current and not undo_update:
        if updater.check_update():
            version, msg_version = updater.latest_version_info()
            echo(f'New version {version}\n{msg_version}')
        else:
            echo(f'No new version found on github release')
            return
    if not skip_download:
        fn = updater.download_version(version=version, force=force, checksign=not no_check_sign)
        echo(f'Download {fn} from github OK')
    if not skip_install:
        if ask_update and not click.confirm('Will we make an update?', default=True):
            echo(f'OK {name} update canceled')
            return
        res, msg = updater.install_update(version=version, force=force, undo_update=undo_update, by_current=by_current)
        echo('Run setup_and_check.bat or mbplugin/standalone/mbp after install')
    echo(f'{"OK" if res else "Fail"} {name}: {msg}')
    sys.exit(1)


@cli.command()
@click.argument('query', type=str, nargs=-1)
@click.pass_context
def db_query(ctx, query):
    'Запуск запроса к БД SQLite, без запроса - показать инфо по таблицам'
    name = 'db-query'
    if store.options('sqlitestore') == '1':
        import dbengine
        db = dbengine.Dbengine()
        if len(query) == 0:
            query1 = "SELECT name FROM sqlite_master WHERE type='table'"
            dbdata = db.conn_execute_fetch(query1)
            echo('Tables:')
            for line in dbdata:
                tbl = line[0]
                cnt = db.conn_execute_00(f"select count(*) from {tbl}")
                echo(f'{tbl} {cnt}')
            return
        query2 = ' '.join(query).replace('select all ', 'select * ')
        cur = db.conn_execute(query2)
        if cur.description is not None:
            dbheaders = list(zip(*cur.description))[0]
            dbdata = cur.fetchall()
            res = [list(dbheaders)] + [i for i in dbdata]
            for line in res:
                echo('\t'.join(map(str, line)))
        if cur.rowcount >= 0:
            echo(f'{cur.rowcount} line affected')
        db.conn.commit()
    echo(f'OK {name}')


@cli.command()
@click.option('-n', '--num', type=int, default=-1)
@click.option('-a', '--alias', type=str, default='')
@click.option('-pl', '--plugin', type=str, default='')
@click.option('-l', '--login', type=str, default='')
@click.pass_context
def bugreport(ctx, num, alias, plugin, login):
    def impersonate(data, line):
        if len(line['password2']) > 0:
            data = data.replace(line['password2'], '********')
        if len(line['number']) > 0:
            data = data.replace(line['number'], 'XXXXXXXXX')
        return data
    'Подготовка данных по запросу баланса для отправки разработчику, задайте либо порядковый номер, либо псевдоним, либо имя плагина и логин'
    name = 'bugreport'
    # echo(f'{num=}, {plugin=}, {alias=}, {login=}')
    phones = store.ini('phones.ini')
    phones.read()
    # Делаем словарь телефонов для поиска
    dp = [dict([('nn', sec)] + list(phones.ini[sec].items())) for sec in phones.ini.sections() if phones.ini[sec].get('Monitor', 'FALSE') == 'TRUE']
    dp = [i for i in dp if i['nn'] == str(num) or num < 0]
    dp = [i for i in dp if i['alias'] == alias or alias == '']
    dp = [i for i in dp if i['region'] == plugin or plugin == '']
    dp = [i for i in dp if i['number'] == login or login == '']
    if len(dp) == 0:
        echo(f'Fail {name}: по указанному фильтру ничего не нашлось.')
        sys.exit(1)
    if len(dp) > 1:
        echo(f'Fail {name}: найдено несколько, должен отфильтроваться только один, укажите точнее')
        sys.exit(2)
    line = dp[0]
    echo(f'Найден один номер {line["alias"]}, составляем bugreport')
    plugin, login = line['region'], line['number']
    plugin_login = line['region'] + '_' + re.sub(r'\W', '_', line['number'].split('/')[0])
    path = store.abspath_join('mbplugin', 'log', f'*{plugin_login}*')
    logname = store.abspath_join('mbplugin', 'log', 'http.log')
    zfn = store.abspath_join('mbplugin', 'log', f'bugreport_{plugin_login}.zip')
    zfn = impersonate(zfn, line)
    with zipfile.ZipFile(zfn, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fn in glob.glob(path):
            if fn.lower().endswith('.zip'):
                continue
            if os.path.splitext(fn) not in ['.log']:
                zf.write(fn, impersonate(os.path.split(fn)[-1], line))
            else:
                with open(fn, errors='ignore') as f:
                    data = f.read()
                    zf.writestr(impersonate(os.path.split(fn)[-1], line), impersonate(data, line).encode('utf-8'))
        with open(logname, errors='ignore') as lf:
            # getbalance_plugin Start {plugin} {login}
            log_all = lf.read().split('\n\n')
            log_flt = [el for el in log_all if f'getbalance_plugin Start {plugin} {login}' in el]
        if len(log_flt) > 0:
            zf.writestr('http.log', impersonate(log_flt[-1], line).encode('utf-8'))
    echo('Логины и пароли из лога удалены, но рекомендуется проверить файлы лога на наличие в них нежелательных для компрометации данных')
    echo(f'Bugreport сохранен в {zfn}')
    echo(f'OK {name}')


@cli.command()
@click.argument('args', nargs=-1)
@click.pass_context
def console(ctx, args):
    'Запуск консоли bash/cmd с окружением для mbplugin - удобно в docker и venv'
    name = 'console'
    store.turn_logging()
    python_path = os.path.split(sys.executable)[0]
    if python_path not in os.environ['PATH'].split(os.pathsep):
        os.environ['PATH'] = python_path + os.pathsep + os.environ['PATH']
    if sys.platform == 'win32':
        os.system(f'cmd {" ".join(args)}')
    else:
        os.system(f'bash {" ".join(args)}')
    echo(f'OK {name}')


@cli.command()
@click.option('-p', '--pure', is_flag=True, help='Запустить чистый браузер без playwright')
@click.option('-f', '--storename', type=str, help='Папка профиля (только в режиме pure)')
@click.argument('url', type=str, default='')
@click.pass_context
def browser(ctx, pure, storename, url):
    'Запуск браузера playwright '
    name = 'browser '
    store.turn_logging()
    if pure:
        if storename is None:
            storename = 'tmp'
        storefolder = store.options('storefolder')
        profile_directory = storename
        user_data_dir = store.abspath_join(storefolder, 'headless', profile_directory)
        import browsercontroller
        if url == '':
            op_var = re.findall(r'^(\w_\w+)_', storename)
            if len(op_var) > 0:
                url = settings.operator_link.get(op_var[0], '')
        os.system(f'{store.start_cmd()} "{browsercontroller.browser_path()}" --password-store=basic "--user-data-dir={user_data_dir}" {url}')
    else: # playwright
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            print(f"{store.options('playwright_stealth')=}")
            if str(store.options('playwright_stealth')) == '1':
                try:
                    from playwright_stealth import stealth_sync
                    stealth_sync(page)
                    print('Stealth mode')
                except Exception:
                    logging.error('Bad turn stealth_sync(page)')
            page.wait_for_timeout(1000)
            if url.strip().lower().startswith('http'):
                page.goto(url)
            page.pause()
            browser.close()
    echo(f'OK {name}')


def mbplugin_ini_md_gen():
    'Генерирует mbplugin_ini.md с актуальным описанием ключей'
    fn_md = os.path.join(os.path.split(os.path.abspath(__file__))[0], '..', 'mbplugin_ini.md')
    import settings
    data = []
    for sec in settings.ini:
        data.append(f'# Секция {sec}')
        for param in settings.ini[sec]:
            if not param.endswith('_'):
                data.append(f'## __{param}__')
                p_default = settings.ini[sec][param]
                p_attr = settings.ini[sec][param + '_']
                data.append(f'Описание: {p_attr["descr"]}  ')
                data.append(f'Значение по умолчанию: {p_default}  ')
                if p_attr['type'] == 'checkbox':
                    data.append(f'Варианты значения {param}: 0 - выключено или 1 - включено  ')
                if p_attr['type'] == 'select':
                    data.append(f'Варианты значения {param}: {p_attr["variants"]}  ')
    prev = open(fn_md, 'r', encoding='utf8').read() if os.path.exists(fn_md) else ''
    if prev == '\n'.join(data):
        echo(f'Nothing has changes in {fn_md}')
        return
    echo(f'Write change to {fn_md}')
    with open(fn_md, mode='w', encoding='utf8', newline='\n') as f:
        f.write('\n'.join(data))

def mbplugin_dockerfile_version():
    'Корректирует версию в dockerfile по версии playwright прописанной в requirements.txt'
    fn_docker = store.abspath_join('mbplugin', 'docker', 'Dockerfile')
    fn_req = store.abspath_join('mbplugin', 'docker', 'requirements.txt')
    with open(fn_req) as f:
        pl_ver_req = re.findall(r'playwright==(\d+\.\d+\.\d+)', f.read())[0]
    with open(fn_docker) as f:
        dockerfile = f.read()
        pl_ver_docker = re.findall(r'mcr.microsoft.com/playwright:v(\d+\.\d+\.\d+)', dockerfile)[0]
    if pl_ver_req == pl_ver_docker:
        echo(f'Nothing has changes in {fn_docker} {pl_ver_req}')
        return
    echo(f'Write change to {dockerfile} {pl_ver_docker} -> {pl_ver_req}')
    if pl_ver_req != pl_ver_docker:
        with open(fn_docker, mode='w', newline='\n') as f:
            dockerfile = re.sub(r'mcr.microsoft.com/playwright:v((\d+\.\d+\.\d+))', f'mcr.microsoft.com/playwright:v{pl_ver_req}', dockerfile)
            f.write(dockerfile)

if __name__ == '__main__':
    store.switch_to_mb_mode()
    cli(obj={})  # pylint: disable=no-value-for-parameter

# ..\python\python -c "import updateengine;updateengine.create_signature()"
# ..\python\python -c "import util;util.mbplugin_ini_md_gen()"
# ..\python\python -c "import util;util.mbplugin_dockerfile_version()"
