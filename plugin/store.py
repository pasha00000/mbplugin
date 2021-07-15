# -*- coding: utf8 -*-
'Модуль для хранения сессий и настроек а также чтения настроек из ini от MobileBalance'
import os, sys, time, io, re, json, pickle, requests, configparser, pprint, zipfile, logging, traceback
from os.path import abspath
import settings


def session_folder(storename):
    'Возвращяет путь к папке хранения сессий'
    storefolder = options('storefolder')     
    os.path.join(storefolder, storename)

def abspath_join(*argv):
    'собираем в путь все переданные куски, если получившийся не абсолютный, то приделываем к нему путь до корня'
    path = os.path.join(*argv)
    if not os.path.isabs(path):
        path = os.path.abspath(os.path.join(settings.mbplugin_root_path, path))
    return path

def path_split_all(path):
    'разбивает путь на список'
    res = []
    while True:
        p1,p2 = os.path.split(path)
        if p1 == path: # Относительный
            res.insert(0, p1)
            break
        elif p2 == path:  # Абсолютный
            res.insert(0, p2)
            break
        else:
            path = p1
            res.insert(0, p2)
    return res

def download_file(url, path='', rewrite=True):
    'Загружает файл по ссылке'
    try:
        local_filename = path
        if len(path) == 0:
            local_filename = url.split('/')[-1]
        local_filename = abspath_join(local_filename)
        if os.path.exists(local_filename) and not rewrite:
            print(f'File {local_filename} exists')
            return local_filename
        # NOTE the stream=True parameter below
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            sz = 0
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): 
                    f.write(chunk)
                    sz += len(chunk)
                    print(f'{local_filename} {sz/1048576:4.2f} MB', end='\r')
            print('\nComplete')
        return local_filename
    except Exception:
        print(f'Error download:\n{"".join(traceback.format_exception(*sys.exc_info()))}')

def read_zip(zipname) -> dict:
    '''Читает zip в словарь, ключи словаря - абсолютные пути на диске, 
    каталоги игнорим, для них у нас в пустых папках флаговые файлы созданы'''
    res = {}
    with zipfile.ZipFile(abspath_join(zipname), 'r') as zf1:
        for zi in zf1.infolist(): # Во временную переменную прочитали
            # Первый элемент пути в зависимости от ветки может называться не так как нам нужно
            fn = abspath_join('mbplugin', *(path_split_all(zi.filename)[1:]))
            if not zi.is_dir():
                res[fn] = zf1.read(zi)
    return res

def version_check_zip(zipname):
    'Проверяет соответствие файлов в архиве и на диске'
    different = []
    for zn,zd in read_zip(abspath_join(zipname)).items():
        if os.path.isfile(zn):
            with open(zn, 'rb') as f:
                data = f.read()
            if data != zd:
                different.append(zn)
    return different

def version_update_zip(new_zipname):
    'Обновляет файлы на диске из архива'
    z_new = read_zip(abspath_join(new_zipname))
    for zn,zd in z_new.items():
        dir_name = os.path.split(zn)[0]
        if not os.path.isdir(dir_name):
            os.makedirs(dir_name, exist_ok=True)
        with open(zn) as f:
            f.write(zd, 'wb')

class Session():
    'Класс для сессии с дополнительными фишками для сохранения и проверки'
    def __init__(self, storename, headers=None):
        self.storename = storename
        self.storefolder = options('storefolder')
        self.pagecounter = 1  # Счетчик страниц для сохранения
        self.json_response = {}  # Сохраняем json ответы
        self.headers = headers
        try:
            with open(os.path.join(self.storefolder, self.storename), 'rb') as f:
                self.session = pickle.load(f)
                self.headers = self.session.headers
        except Exception:
            self.session = requests.Session()
            if self.headers:
                self.session.headers.update(self.headers)

    def update_headers(self, headers):
        self.headers.update(headers)
        self.session.headers.update(self.headers)

    def drop_and_create(self, headers=None):
        'удаляем сессию и создаем новую'
        try:
            os.remove(os.path.join(self.storefolder, self.storename))
        except Exception:
            pass
        self.session = requests.Session()
        if headers:
            self.headers = headers
        if self.headers:
            self.session.headers.update(self.headers)

    def save_session(self):
        'Сохраняем сессию в файл'
        with open(os.path.join(self.storefolder, self.storename), 'wb') as f:
            pickle.dump(self.session, f)

    def save_response(self, url, response):
        'debug save response'
        # Сохраняем по старинке в режиме DEBUG каждую страницу в один файл
        if not hasattr(response, 'content'):
            return
        if options('logginglevel') == 'DEBUG':
            fld = options('loggingfolder')
            fn = os.path.join(fld, f'{self.storename}_{self.pagecounter}.html')
            open(fn, mode='wb').write(response.content)
        # Новый вариант сохранения - все json в один файл
        if options('logginglevel') == 'DEBUG' or str(options('log_responses')) == '1':
            try:
                js = response.json()
                self.json_response[f'{url}_{self.pagecounter}'] = js
                text = '\n\n'.join([f'{k}\n{pprint.PrettyPrinter(indent=4).pformat(v)}' for k, v in self.json_response.items()])
                open(os.path.join(options('loggingfolder'), self.storename + '.log'), 'w', encoding='utf8', errors='ignore').write(text)
            except Exception:
                pass
        self.pagecounter += 1

    def get(self, url, **kwargs):
        response = self.session.get(url, **kwargs)
        self.save_response(url, response)
        return response
        
    def post(self, url, data=None, json=None, **kwargs):
        response = self.session.post(url, data, json, **kwargs)
        self.save_response(url, response)
        return response

    def put(self, url, data=None, **kwargs):
        response = self.session.put(url, data, **kwargs)
        self.save_response(url, response)
        return response


def options(param, default=None, section='Options', listparam=False, mainparams={}):
    'Читаем параметр из mbplugin.ini либо дефолт из settings'
    'Если listparam=True, то читаем список из всех, что начинается на param'
    'mainparams - перекрывает любые другие варианты, если в нем присутствует - берем его'
    if param in mainparams and listparam == False:
        return mainparams[param]
    if default is None:
        default = settings.ini[section].get(param.lower(), None)
    options_all_sec = ini().read()
    if section in options_all_sec:
        options_sec = options_all_sec[section]
    else:
        options_sec = {}
    if listparam:
        return [v for k,v in options_sec.items() if k.startswith(param)]
    else:
        return options_sec.get(param, default)
    
class ini():
    def __init__(self, fn=settings.mbplugin_ini):
        'файл mbplugin.ini ищем в вышележащих папках либо в settings.mbplugin_root_path если он не пустой'
        'остальные ini ищем в пути прописанном в mbplugin.ini\\MobileBalance\\path'
        'Все пути считаются относительными папки где лежит сам mbplugin.ini, если не указано иное'
        self.ini = configparser.ConfigParser()
        self.fn = fn
        self.inipath = abspath_join(settings.mbplugin_root_path, self.fn)
            
    def find_files_up(self, fn):
        'Ищем файл вверх по дереву путей'
        'Для тестов можно явно указать папку с mbplugin.ini в settings.mbplugin_root_path '
        # TODO пока оставили чтобы не ломать тесты, потом уберем 
        return abspath_join(settings.mbplugin_root_path, fn)
        
    def read(self):
        'Читаем ini из файла'
        'phones.ini и phones_add.ini- нечестный ini читать приходится с извратами'
        'replace [Phone] #123 -> [123]'
        'Для чтения phones.ini с добавлением данных из phones_add.ini см метод ini.phones'
        if os.path.exists(self.inipath):
            if self.fn.lower() == 'phones.ini' or self.fn.lower() == 'phones_add.ini':
                with open(self.inipath) as f_ini:
                    prep1 = re.sub(r'(?usi)\[Phone\] #(\d+)', r'[\1]', f_ini.read())
                # TODO костыль N1, мы подменяем p_pluginLH на p_plugin чтобы при переключении плагина не разъезжались данные
                prep2 = re.sub(r'(?usi)(Region)(\s*=\s*p_\S+)(LH)', r'\1\2\n\1_orig\2\3', prep1)
                # TODO костыль N2, у Number то что идет в конце вида <пробел>#<цифры> это не относиться к логину а 
                # сделано для уникальности логинов - выкидываем, оно нас только сбивает - мы работаем по паре Region_Number
                # Первоначальное значение сохраняется в Phone_orig и Region_orig
                prep3 = re.sub(r'(?usi)(Number)(\s*=\s*\S+)( #\d+)', r'\1\2\n\1_orig\2\3', prep2)
                self.ini.read_string(prep3)
            else:
                self.ini.read(self.inipath)
        elif not os.path.exists(self.inipath) and self.fn.lower() == settings.mbplugin_ini:
            self.create()
            self.write()
        elif not os.path.exists(self.inipath) and self.fn.lower() == 'phones_add.ini':
            self.ini.read_string('')  # Если нет - тихо вернем пустой
        else:
            raise RuntimeError(f'Not found {self.fn}')
        return self.ini

    def create(self):
        'Только создаем в памяти, но не записываем'
        # Создаем mbplugin.ini - он нам нужен для настроек и чтобы знать где ini-шники от mobilebalance
        # mbpath = self.find_files_up('phones.ini')
        mbpath = abspath_join(settings.mbplugin_root_path, 'phones.ini')
        if not os.path.exists(mbpath):
            # Если нашли mobilebalance - cоздадим mbplugin.ini и sqlite базу там же где и ini-шники mobilebalance
            print(f'Not found phones.ini in {settings.mbplugin_root_path}')
            raise RuntimeError(f'Not found phones.ini')
        # создадим mbplugin.ini над папкой mbplugin
        dbpath = settings.ini['Options']['dbfilename']
        self.ini['Options'] = {'logginglevel': settings.ini['Options']['logginglevel'],
                          'sqlitestore': settings.ini['Options']['sqlitestore'],
                          'dbfilename': dbpath,
                          'createhtmlreport': settings.ini['Options']['createhtmlreport'],
                          'balance_html': abspath_join(settings.ini['Options']['balance_html']),
                          'updatefrommdb': settings.ini['Options']['updatefrommdb'],
                          'updatefrommdbdeep': settings.ini['Options']['updatefrommdbdeep'],
                          }
        self.ini['HttpServer'] = {'port': settings.ini['HttpServer']['port'],
                             'host': settings.ini['HttpServer']['host'],
                             'table_format': settings.ini['HttpServer']['table_format']
                             }    

    def save_bak(self):
        'Сохраняем резервную копию файла в папку с логами в zip'
        if not os.path.exists(self.inipath): # Сохраняем bak, только если файл есть
            return
        # Делаем резервную копию ini перед сохранением
        undozipname = abspath_join(options('storefolder'), 'mbplugin.ini.bak.zip')
        arc = []
        if os.path.exists(undozipname):
            # Предварительно читаем сохраненные варианты, открываем на чтение
            with zipfile.ZipFile(undozipname, 'r', zipfile.ZIP_DEFLATED) as zf1:
                for i in zf1.infolist(): # Во временную переменную прочитали
                    arc.append((i, zf1.read(i)))
        arc = sorted(arc, reverse=True, key=lambda i: i[0].filename)[0:int(options('httpconfigeditundo'))]
        name_bak = f'{os.path.split(self.inipath)[-1]}_{time.strftime("%Y%m%d%H%M%S", time.localtime())}'
        # Если быстро менять конфиг - то успеваем в одну секунду сохранить несколько раз - это лишнее
        # Если в эту секунду уже сохраняли - пропускаем
        if name_bak in [i[0].filename for i in arc]:
            print('We create undo too often - lets skip this one')
            return
        with zipfile.ZipFile(undozipname+'~tmp', 'w', zipfile.ZIP_DEFLATED) as zf2:
            # Sic! Для write write(filename, arcname) vs writestr(arcname, data)
            zf2.write(self.inipath, f'{name_bak}')
            for a_name, a_data in arc:
                zf2.writestr(a_name, a_data)
        if os.path.exists(undozipname):
            os.remove(undozipname)  # Удаляем первоначальный файл
        os.rename(undozipname+"~tmp", undozipname) # Переименовываем временный на место первоначального

    def write(self):
        '''Сохраняем только mbplugin.ini и phones.ini для остальных - игнорим
        phones.ini всегда сохраняем в phones.ini, без phones_add.ini, если есть phones_add.ini не работаем 
        '''
        def ini_write_to_string(ini: configparser.ConfigParser) -> str:
            sf = io.StringIO()
            ini.write(sf)
            return sf.getvalue()
        if not (self.fn.lower() == settings.mbplugin_ini or self.fn.lower() == 'phones.ini' and str(options('phone_ini_save')) =='1'):
            return  # only mbplugin.ini
        data = ini_write_to_string(self.ini)
        if self.fn.lower() == 'phones.ini': # для phones.ini отдельно приседаем
            t_ini = configparser.ConfigParser()  # Делаем копию ini чтобы не портить загруженный оригинал
            t_ini.read_string(data)
            for sec in t_ini.sections():  # number_orig -> number, region_orig -> region
                for key in t_ini[sec]: 
                    if key+'_orig' in t_ini[sec]:
                        t_ini[sec][key] = t_ini[sec][key+'_orig']
                        del t_ini[sec][key+'_orig']
            data = re.sub(r'(?m)^\[(\d+)\]$', r'[Phone] #\1', ini_write_to_string(t_ini))  # [36] -> [Phone] #36
            for key in 'Region,Monitor,Alias,Number,Password,mdOperation,mdConstant,PauseBeforeRequest,ShowInBallon,BalanceNotChangedMoreThen,BalanceChangedLessThen,BalanceLessThen,TurnOffLessThen,Password2'.split(','):
                data = data.replace(f'{key.lower()} =', f'{key:20} =')
            #print(data)
            #return
        raw = data.splitlines()  # инишник без комментариев (прогнали через честное сохранение)
        if os.path.exists(self.inipath):  # Если файл ini на диске есть сверяем с предыдущей версией
            self.save_bak()
            # TODO если сохраняем коменты (коменты попадут куда надо если меняем не больше одной строчки за раз):
            with open(self.inipath, encoding='cp1251') as f_ini_r:
                for num,line in enumerate(f_ini_r.read().splitlines()):
                    if line.startswith(';'):
                        raw.insert(num, line)
        with open(self.inipath, encoding='cp1251', mode='w') as f_ini_w:
            f_ini_w.write('\n'.join(raw))
        # TODO Если просто сохраняем то так
        # self.ini.write(open(self.inipath, 'w'))

    def ini_to_json(self):
        'Преобразуем ini в js для редактора editcfg'
        result = {}
        for sec in self.ini.values():
            if sec.name != 'DEFAULT':
                # Кидаем ключи из ini после Добавляем дефолтные ключи из settings если их не было в ini
                # TODO продумать, может их помечать цветом и сделать кнопку вернуть к дефолту, т.е. удалить ключ из ini
                for key,val in list(sec.items()) + list(settings.ini.get(sec.name, {}).items()):
                    if key.endswith('_'):
                        continue
                    param = settings.ini.get(sec.name, {}).get(key+'_', {})
                    param = {k:v for k,v in param.items() if k not in ['validate']}
                    line = {'section': sec.name, 'id': key, 'type': 'text', 'descr': f'DESC {sec.name}_{key}', 
                            'value': val, 'default': key not in sec, 'default_val': settings.ini.get(sec.name, {}).get(key, None)}
                    line.update(param)
                    if f'{sec.name}_{key}' not in result:
                        result[f'{sec.name}_{key}'] = line
        return json.dumps(result, ensure_ascii=False)

    def phones(self):
        'Читает phones.ini добавляет данные из phones_add.ini дополнительную инфу'
        'И возвращает словарь с ключами в виде пары вида (number,region)'
        if self.fn.lower() != 'phones.ini':
            raise RuntimeError(f'{self.fn} is not phones.ini')
        # Читаем вспомогательный phones_add.ini - из него возьмем данные если они там есть, они перекроют данные в phones.ini
        phones_add = ini('phones_add.ini').read()
        data = {}
        for secnum,el in self.read().items():
            if secnum.isnumeric() and 'Monitor' in el:
                key = (re.sub(r' #\d+','',el['Number']),el['Region'])
                data[key] = {}
                data[key]['NN'] = int(secnum)
                data[key]['Alias'] = el.get('Alias','')
                data[key]['Region'] = el.get('Region','')
                data[key]['Number'] = el.get('Number','')
                data[key]['PhoneDescription'] = el.get('PhoneDescription','')
                data[key]['Monitor'] = el.get('Monitor','')
                data[key]['BalanceLessThen'] = float(el.get('BalanceLessThen', options('BalanceLessThen')))
                data[key]['TurnOffLessThen'] = int(el.get('TurnOffLessThen', options('TurnOffLessThen')))
                data[key]['BalanceNotChangedMoreThen'] = int(el.get('BalanceNotChangedMoreThen', options('BalanceNotChangedMoreThen')))
                data[key]['BalanceChangedLessThen'] = int(el.get('BalanceChangedLessThen', options('BalanceChangedLessThen')))
                data[key]['Password2'] = el.get('Password2','')
                if secnum in phones_add:
                    try:
                        # Проблема - configparser возвращает ключи в lowercase - так что приходится перебирать 
                        # ключи чтобы не оказалось два одинаковых ключа с разным кейсом
                        for k in data[key].keys():
                            if k in phones_add[secnum]:
                                data[key][k] = phones_add[secnum][k]
                    except Exception:
                        raise RuntimeError(f'Parse phones_add.ini error in section{secnum}')
        return data


def read_stocks(stocks_name):
    'Читаем список стоков для плагина stock.py из mbplugin.ini'
    ini_all_sec = ini().read()
    if 'stocks_'+stocks_name not in ini_all_sec:
        raise RuntimeError(f'section {"stocks_"+stocks_name} not in mbplugin.ini')
    stock_sec_ini = ini_all_sec['stocks_'+stocks_name]
    stocks = {'stocks': [], 'remain': {}, 'currenc': ''}
    items = stock_sec_ini.items()
    stocks_str = [list(map(str.strip, v.split(','))) for k, v in items if k.startswith('stock')]
    remain_str = [list(map(str.strip, v.split(','))) for k, v in items if k.startswith('remain')]
    stocks['currenc'] = stock_sec_ini['currenc'].strip()
    stocks['stocks'] = [(i[0].upper(), int(i[1]), i[2].upper()) for i in stocks_str if len(i) == 3 and i[1].isnumeric()]
    stocks['remain'] = {i[0].upper(): int(i[1]) for i in remain_str if len(i) == 2 and i[1].isnumeric()}
    return stocks


def result_to_xml(result):
    'Конвертирует словарь результатов в готовый к отдаче вид '
    # Коррекция SMS и Min (должны быть integer)
    if 'SMS' in result:
        result['SMS'] = int(result['SMS'])
    if 'Min' in result:
        result['Min'] = int(result['Min'])
    for k, v in result.items():
        if type(v) == float:
            result[k] = round(v, 2)  # Чтобы не было паразитных микрокопеек
    body = ''.join([f'<{k}>{v}</{k}>' for k, v in result.items()])
    return f'<Response>{body}</Response>'


def result_to_html(result):
    'Конвертирует словарь результатов в готовый к отдаче вид '
    # Коррекция SMS и Min (должны быть integer)
    if 'SMS' in result:
        result['SMS'] = int(result['SMS'])
    if 'Min' in result:
        result['Min'] = int(result['Min'])
    body = json.dumps(result, ensure_ascii=False)
    return f'<html><meta charset="windows-1251"><p id=response>{body}</p></html>'    


def logging_restart():
    'Останавливаем логирование и откидываем в отдельный файл'
    'Чтобы можно было почистить'
    filename = options('logginghttpfilename')
    filename_new = filename + time.strftime('%Y%m%d%H%M%S.log',time.localtime())
    logging.shutdown()
    os.rename(filename, filename_new)
    logging.info(f'Old log was renamed to {filename_new}')


def ini_by_expression(expression):
    '''берем из ini по path вида ini\Options\sqlitestore - нужно для cmd обращений к ini
    если указано ini\Options\sqlitestore - возвращает set sqlitestore=ЗНАЧЕНИЕ
    если указано ini\Options\sqlitestore=1 - устанавливает в ini'''
    mbplugin_ini=ini()
    mbplugin_ini.read()
    path = expression
    if '=' in expression:
        path, value = expression.split('=')
        _, section, key = path.split('\\')
        mbplugin_ini.ini[section][key] = value
        if value == 'default':
            del mbplugin_ini.ini[section][key]
        mbplugin_ini.write()
    else:
        _, section, key = path.split('\\')
    return f'set {key}={options(key, section=section)}'


def turn_logging(httplog=False, logginglevel=None):
    'Включение логирования'
    file_log = logging.FileHandler(options('logginghttpfilename' if httplog else 'loggingfilename'))
    if logginglevel is None:
        logginglevel = options('logginglevel')
    handlers = (file_log,)
    if str(options('logconsole')) == '1':
        console_out = logging.StreamHandler()
        handlers = (file_log, console_out)
    logging.basicConfig(
        handlers=handlers,
        level = logginglevel,
        format = options('loggingformat'))


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print('Module store')
    else:
        # = в коммандной строке делит аргументы - чиним
        expression = sys.argv[1]
        if len(sys.argv) == 3:
            expression = sys.argv[1] + '=' + sys.argv[2]
        print(ini_by_expression(expression))

    # print(list(ini('phones.ini').read().keys()))
    # print(list(ini('options.ini').read().keys()))
    # print(list(ini('mbplugin.ini').read().keys()))

    #ini = ini().read()
    #if ini['MobileBalance']['path'] == '':
    #    print('MobileBalance folder unknown')
    #print(list(ini('phones.ini').read().keys()))

    #stocks_name = 'broker_ru'
    #print(read_stocks(stocks_name))

    # import io;f = io.StringIO();ini.write(f);print(f.getvalue())
    #{'STOCKS':(('AAPL',1,'Y'),('TATNP',16,'M'),('FXIT',1,'M')), 'REMAIN': {'USD':5, 'RUB':536}, 'CURRENC': 'USD'}
    #p=ini('phones.ini').read()
    # import store;ini=store.ini();ini.read();ini.ini['Options']['httpconfigedit']='1';ini.write()
