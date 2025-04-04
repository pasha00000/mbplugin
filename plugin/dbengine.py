# -*- coding: utf8 -*-
''' Автор ArtyLa
Модуль для работы с базами
Для интеграции с базой MDB необходимо установить 32битный ODBC драйвер для MDB AccessDatabaseEngine.exe:
Скачать можно отсюда:
https://www.microsoft.com/en-us/download/details.aspx?id=54920
Объяснение, почему не 32 битный python не работает с 64 битным ODBC и наоборот
https://stackoverflow.com/questions/45362440/32bit-pyodbc-for-32bit-python-3-6-works-with-microsofts-64-bit-odbc-driver-w
set up some constants

'''
import math, time, os, sys, re, logging, sqlite3, datetime, json, typing
import settings, store

DB_SCHEMA = ['''
CREATE TABLE IF NOT EXISTS Phones (
    NN INTEGER NOT NULL DEFAULT NULL PRIMARY KEY AUTOINCREMENT,
    [PhoneNumber] [nvarchar] (150), -- COLLATE Cyrillic_General_CI_AS NULL ,
    [MBPhoneNumber] [nvarchar] (150), -- COLLATE Cyrillic_General_CI_AS NULL ,
    Operator [nchar] (50), -- plugin name
    QueryDateTime timestamp DEFAULT NULL,
    SpendBalance [float] NULL ,
    KreditLimit [float] NULL ,
    UslugiOn [nchar] (50), -- COLLATE Cyrillic_General_CI_AS NULL ,
    Currenc [nchar] (10), -- COLLATE Cyrillic_General_CI_AS NULL ,
    [Balance] [float] NULL ,
    [Balance2] [float] NULL ,
    [Balance3] [float] NULL ,
    [Average] [real] NULL ,
    [TurnOff] [smallint] NULL ,
    [Recomend] [real] NULL ,
    [SMS] [smallint] NULL ,
    [Minutes] [smallint] NULL ,
    [USDRate] [real] NULL ,
    [LicSchet] [nchar] (20), -- COLLATE Cyrillic_General_CI_AS NULL ,
    [UserName] [nchar] (50), -- COLLATE Cyrillic_General_CI_AS NULL ,
    [BalDelta] [real] NULL ,
    [JeansExpired] [smallint] NULL ,
    [ObPlat] [real] NULL ,
    [BeeExpired] [nchar] (20), -- COLLATE Cyrillic_General_CI_AS NULL , -- BalExpired Expired
    [RealAverage] [real] NULL ,
    [Seconds] [smallint] NULL ,
    [TarifPlan] [nchar] (50), -- COLLATE Cyrillic_General_CI_AS NULL ,
    [BlockStatus] [nchar] (50), -- COLLATE Cyrillic_General_CI_AS NULL ,
    [MinSonet] [real] NULL ,
    [MinLocal] [real] NULL ,
    [Internet] [real] NULL ,
    [TurnOffStr] [nchar] (30), -- COLLATE Cyrillic_General_CI_AS NULL ,
    [SpendMin] [real] NULL ,
    [PhoneReal] [nchar] (20), -- COLLATE Cyrillic_General_CI_AS NULL ,
    [BalanceRUB] [real] NULL ,
    [SMS_USD] [real] NULL ,
    [SMS_RUB] [real] NULL ,
    [InternetUSD] [real] NULL ,
    [InternetRUB] [real] NULL ,
    [Contract] [nchar] (20), -- COLLATE Cyrillic_General_CI_AS NULL ,
    [MinAverage] [real] NULL ,
    [BalDeltaQuery] [real] NULL ,
    [MinDelta] [real] NULL ,
    [MinDeltaQuery] [real] NULL ,
    [NoChangeDays] [int] NULL ,
    [AnyString] [nchar] (250), -- COLLATE Cyrillic_General_CI_AS NULL ,
    [CalcTurnOff] [int] NULL
);''', '''
CREATE TABLE IF NOT EXISTS Flags (
    [key] [nvarchar] (150) PRIMARY KEY,
    [value] [nvarchar] (150) NULL
);''', '''
CREATE TABLE IF NOT EXISTS Responses (
    [key] [nvarchar] (150) PRIMARY KEY,
    [value] [nvarchar] (10000) NULL
);''', '''
CREATE TABLE IF NOT EXISTS phones_delta AS select * from phones limit 0;
--
-- CREATE INDEX idx_PhoneNumber_Operator ON Phones (PhoneNumber,Operator);
-- CREATE INDEX idx_QueryDateTime ON Phones (QueryDateTime);
''']
PhonesHText = {
    'NN': 'NN',
    'Alias': 'Псевдоним',
    'PhoneNumber': 'Номер',
    'PhoneNumberFormat1': 'Номер',
    'PhoneNumberFormat2': 'Номер',
    'MBPhoneNumber': 'Номер как в MB',
    'Operator': 'Оператор',
    'QueryDateTime': 'Время запроса',
    'SpendBalance': 'SpendBalance',
    'KreditLimit': 'Кр. лимит',
    'UslugiOn': 'Услуги',
    'Currenc': 'Валюта',
    'Balance': 'Баланс',
    'Balance2': 'Баланс2',
    'Balance3': 'Баланс3',
    'Average': 'Average',
    'TurnOff': 'TurnOff',
    'Recomend': 'Recomend',
    'SMS': 'SMS',
    'Minutes': 'Минут',
    'USDRate': 'USDRate',
    'LicSchet': 'Л.счет',
    'UserName': 'ФИО',
    'BalDelta': 'Delta (день)',
    'JeansExpired': 'JeansExpired',
    'ObPlat': 'ObPlat',
    'BeeExpired': 'BeeExpired',
    'RealAverage': '$/День(Р)',
    'Seconds': 'Секунд',
    'TarifPlan': 'Тариф. план',
    'BlockStatus': 'Статус блок.',
    'MinSonet': 'MinSonet',
    'MinLocal': 'MinLocal',
    'Internet': 'Инт.трафик',
    'TurnOffStr': 'TurnOffStr',
    'SpendMin': 'SpendMin',
    'PhoneReal': 'PhoneReal',
    'BalanceRUB': 'BalanceRUB',
    'SMS_USD': 'SMS_USD',
    'SMS_RUB': 'SMS_RUB',
    'InternetUSD': 'InternetUSD',
    'InternetRUB': 'InternetRUB',
    'Contract': 'Contract',
    'MinAverage': 'Мин/день ср',
    'BalDeltaQuery': 'Delta (запрос)',
    'MinDelta': 'Мин/день',
    'MinDeltaQuery': 'Мин Delta (запрос)',
    'NoChangeDays': 'Дней без изм.',
    'AnyString': 'AnyString',
    'CalcTurnOff': 'Откл (Р)',
}

addition_phone_fields = {'MBPhoneNumber': '[nvarchar] (150)'}
addition_indexes = ['idx_QueryDateTime ON Phones (QueryDateTime ASC)',
                    'idx_Phonenumber ON Phones (PhoneNumber)',
                    'idx_MBPhonenumber ON Phones (MBPhoneNumber)']
addition_queries = [
    "delete from phones where phonenumber like 'p_%' or (phonenumber='tinkoff' and operator='???') or operator in ('#01','#02')"
    ]


class Dbengine():
    'Класс для работы с базой, внутри одного экземпляра используется только один курсор, для нескольких курсоров используйте несколько экземпляров'

    _need_updatescheme = True

    def __new__(cls, *args, **kwargs):  # catching the first launch and forced initialization
        instance = super().__new__(cls)
        instance._update_scheme = cls._need_updatescheme
        if cls._need_updatescheme:
            cls._need_updatescheme = False
        return instance
    
    def __init__(self, dbname=None, updatescheme=False, fast=False, row_factory=None, make_headers=True):
        'fast - быстрее, но менее безопасно'
        if dbname is None:
            dbname = store.abspath_join(settings.mbplugin_ini_path, 'BalanceHistory.sqlite')
        self.dbname = dbname
        self.cur_description = ()
        logging.debug(f'Db open {self.dbname}')
        self.conn = sqlite3.connect(self.dbname)  # detect_types=sqlite3.PARSE_DECLTYPES
        if row_factory is not None:
            self.conn.row_factory = row_factory
        # self.cur = self.conn.cursor()  # TODO it's wrong
        cache_size = int(store.options('sqlite_cache_size'))
        if cache_size != 0:
            self.conn.execute(f'PRAGMA cache_size = {cache_size};')
        if fast:
            self.conn.execute('PRAGMA synchronous = OFF;')
            self.conn.commit()
        if self._update_scheme or updatescheme:
            self.check_and_add_addition()
        if make_headers:
            description = self.conn.execute('SELECT * FROM phones limit 1;').description
            self.phoneheader = list(zip(*description))[0]

    def __enter__(self):
        logging.debug(f'Db __enter__ {self.dbname}')
        return self

    def __exit__(self, type, value, traceback):
        logging.debug(f'Db __exit__ close {self.dbname}')
        self.conn.close()

    def conn_execute(self, query, *args, **kwargs):
        'Обертка для cur.execute(...) для UPDATE/INSERT/DELETE c логированием и таймингом'
        t_start = time.process_time()
        cur = self.conn.execute(query, *args, **kwargs)
        logging.debug(f'{query} {args} {kwargs}')
        logging.debug(f'Execution time {time.process_time()-t_start:.6f}')
        return cur

    def conn_execute_fetch(self, query, *args, **kwargs):
        'Обертка для cur.execute(...).fetchall() для SELECT c логированием и таймингом сразу возвращает list с результатом'
        t_start = time.process_time()
        cur = self.conn.execute(query, *args, **kwargs)
        self.cur_description = cur.description
        res = cur.fetchall()
        logging.debug(f'{query} {args} {kwargs}')
        logging.debug(f'Execution time {time.process_time()-t_start:.6f}')
        return res

    def conn_execute_00(self, query, *args, **kwargs):
        'cur.execute(...).fetchall()[0][0] '
        res = self.conn_execute_fetch(query, *args, **kwargs)
        if len(res) != 0:
            return res[0][0]
        return None

    def write_result(self, plugin, login, result, commit=True):
        'Записывает результат в базу'
        # Делаем копию, чтобы не трогать оригинал
        result2 = {k: v for k, v in result.items()}
        # Исправляем поля которые в response называются не так как в базе
        if type(result2['Balance']) == str:
            result2['Balance'] = float(result2['Balance'])
        if not math.isfinite(result2['Balance']):
            raise RuntimeError(f"Balance is {result2['Balance']}, it is not correct")
        if 'Currency' in result2:  # Currency -> Currenc
            result2['Currenc'] = result2['Currency']
        if 'Min' in result2:  # Min -> Minutes
            result2['Minutes'] = result2['Min']
        if 'BalExpired' in result2:  # BalExpired -> BeeExpired
            result2['BeeExpired'] = result2['BalExpired']
        if 'Expired' in result2:  # Expired -> BeeExpired
            result2['BeeExpired'] = result2['Expired']
        # Фильтруем только те поля, которые есть в таблице phone
        line = {k: v for k, v in result2.items() if k in self.phoneheader}
        # Добавляем расчетные поля и т.п.
        line['Operator'] = plugin
        line['PhoneNumber'] = login  # PhoneNumber=PhoneNum
        line['QueryDateTime'] = datetime.datetime.now().replace(microsecond=0)  # no microsecond
        # Дней без изм.
        query = f"select cast(julianday('now')-julianday(max(QueryDateTime)) as integer) from phones where phonenumber='{login}' and operator='{plugin}' and abs(balance-({result2['Balance']}))>0.02"
        line['NoChangeDays'] = self.conn_execute_00(query)
        if line['NoChangeDays'] is None:
            # Если баланс не менялся ни разу - то ориентируемся на самый первый запрос баланса
            query = f"select cast(julianday('now')-julianday(min(QueryDateTime)) as integer) from phones where phonenumber='{login}' and operator='{plugin}' "
            line['NoChangeDays'] = self.conn_execute_00(query)
        # Если записей по этому номеру совсем нет (первый запрос), тогда просто ставим 0
        line['NoChangeDays'] = line['NoChangeDays'] if line['NoChangeDays'] is not None else 0
        try:
            options_ini = store.ini('Options.ini').read()
            average_days = int(options_ini['Additional']['AverageDays'])
        except Exception:
            average_days = int(store.options('average_days'))
        qres = self.conn_execute_fetch(f"select {line['Balance']}-balance from phones where phonenumber='{login}' and operator='{plugin}' and QueryDateTime>date('now','-{average_days} day') and strftime('%Y%m%d', QueryDateTime)<>strftime('%Y%m%d', date('now')) order by QueryDateTime desc limit 1")
        if qres != []:
            line['BalDelta'] = round(qres[0][0], 2)  # Delta (день)
        # qres = self.conn_execute_fetch(f"select {line['Balance']}-balance from phones where phonenumber='{login}' and operator='{plugin}' order by QueryDateTime desc limit 1")
        qres = self.conn_execute_fetch(f"select avg(b) from (select min(BalDelta) b from phones where phonenumber='{login}' and operator='{plugin}' and QueryDateTime>date('now','-{average_days} day') group by strftime('%Y%m%d', QueryDateTime))")
        if qres != [] and qres[0][0] is not None:
            line['RealAverage'] = round(qres[0][0], 2)  # $/День(Р)
        if line.get('RealAverage', 0.0) < 0:
            line['CalcTurnOff'] = round(-line['Balance'] / line['RealAverage'], 2)
        last_line_raw = self.conn_execute_fetch(f"select * from phones where phonenumber='{login}' and operator='{plugin}' order by QueryDateTime desc limit 1")
        if last_line_raw != []:
            last_line = {k[0]:v for k,v in zip(self.cur_description,last_line_raw[0])}
            line['BalDeltaQuery'] = round(line['Balance']-last_line['Balance'], 2)  # Delta (запрос)
            try:
                delta = {}  # готовим дельту phones_delta
                for key in line:
                    if key in ['QueryDateTime', 'Operator', 'PhoneNumber', 'NoChangeDays']:  # эти копируем
                        delta[key] = line[key]
                    if key in ['AnyString', 'BlockStatus', 'Currenc', 'LicSchet', 'TarifPlan', 'TurnOffStr', 'UserName', 'UslugiOn']:  # строки 
                        if str(last_line.get(key, "")) != str(line[key]):
                            delta[key] = f'{last_line.get(key, "")} -> {line[key]}'
                    if key in ['Balance', 'Balance2', 'Balance3', 'SpendBalance', 'KreditLimit', 'Average', 'TurnOff', 'Recomend', 'SMS', 'SpendMin', 'ObPlat', 'Internet', 'Minutes']:  # числа
                        prev_v = last_line.get(key, None)
                        if not(type(prev_v) is int or type(prev_v) is float):
                            prev_v = 0
                        if last_line.get(key, 0) != line[key] and (type(line[key]) is int or type(line[key]) is float):
                            delta[key] = line[key] - prev_v
                self.conn_execute(f"delete from phones_delta where phonenumber='{login}' and operator='{plugin}'")
                self.conn_execute(f'insert into phones_delta ({",".join(delta.keys())}) VALUES ({",".join(list("?"*len(delta)))})', list(delta.values()))
            except Exception:
                logging.exception('Error in calculate delta')
        self.conn.execute(f'insert into phones ({",".join(line.keys())}) VALUES ({",".join(list("?"*len(line)))})', list(line.values()))
        result2['QueryDateTime'] = datetime.datetime.now().strftime('%Y.%m.%d %H:%M:%S')
        self.conn_execute('REPLACE INTO responses(key,value) VALUES(?,?)', [f'{plugin}_{login}', json.dumps(result2, ensure_ascii=False)])
        if commit:
            self.conn.commit()

    def report(self):
        ''' Генерирует отчет по последнему состоянию телефонов'''
        reportsql = f'''select * from phones where NN in (select NN from (SELECT NN,max(QueryDateTime) FROM Phones GROUP BY PhoneNumber,Operator)) order by PhoneNumber,Operator'''
        dbdata = self.conn_execute_fetch(reportsql)
        dbheaders = list(zip(*self.cur_description))[0]
        phones = store.ini('phones.ini').phones()
        dbdata.sort(key=lambda line: (phones.get(line[0:2], {}).get('NN', 999)))
        # округляем float до 2х знаков
        dbdata = [tuple([(round(i, 2) if type(i) == float else i) for i in line]) for line in dbdata]
        table = []  # результат - каждая строчка словарь элементов
        for line in dbdata:
            row = dict(zip(dbheaders, line))
            pair = (row['PhoneNumber'], row['Operator'])  # Пара PhoneNumber,Operator
            row['Alias'] = phones.get(pair, {}).get('Alias', 'Unknown')
            row['NN'] = phones.get(pair, {}).get('NN', 999)
            row['PhoneNumberFormat1'] = row['PhoneNumberFormat2'] = row['PhoneNumber']
            if type(row['PhoneNumber']) == str and row['PhoneNumber'].isdigit():
                # форматирование телефонных номеров
                row['PhoneNumberFormat1'] = re.sub(r'\A(\d{3})(\d{3})(\d{4})\Z', '(\\1) \\2-\\3', row['PhoneNumber'])
                row['PhoneNumberFormat2'] = row['PhoneNumberFormat1'].replace(' ', '')
            table.append(row)
        return table

    def history(self, phone_number, operator, days=7, lastonly=1, pkey=None):
        'Генерирует исторические данные по номеру телефона, pkey нужен чтобы взять индивидуальные настройки, для телефона если они есть'
        if days == 0:
            return []
        historysql = f'''select * from phones where phonenumber=? and operator=? and QueryDateTime>date('now','-'|| ? ||' day') order by QueryDateTime desc'''
        dbdata = self.conn_execute_fetch(historysql, [phone_number, operator, days])
        dbheaders = list(zip(*self.cur_description))[0]
        dbdata_sets = [set(el) for el in zip(*dbdata)]  # составляем список уникальных значений по каждой колонке
        dbdata_sets = [{i for i in el if str(i).strip() not in ['', 'None', '0.0', '0']} for el in dbdata_sets]  # подправляем косяки
        if len(dbdata_sets) == 0:  # Истории нет - возвращаем пустой
            return []
        qtimes_num = dbheaders.index('QueryDateTime')
        qtimes = [line[qtimes_num] for line in dbdata]  # Список всех времен получения баланса
        qtimes_max = {max([k for k in qtimes if k.startswith(j)]) for j in {i.split()[0] for i in qtimes}}  # Последние даты получения баланса за сутки
        table = []  # результат - каждая строчка словарь элементов
        fields = [i.strip() for i in store.options('HoverHistoryFormat', pkey=pkey).split(',')]
        # выкидываем неинтересные колонки Там где только нули и None
        fields = [i for i in fields if i in dbheaders and dbdata_sets[dbheaders.index(i)] != set()]
        for line in dbdata:
            row = dict(zip(dbheaders, line))
            if str(lastonly) == '0' or row['QueryDateTime'] in qtimes_max:  # фильтруем данные по qtimes_max
                table.append({k: row[k] for k in fields if k in row})
        return table[::int(store.options('SkipDay', pkey=pkey)) + 1]

    def check_and_add_addition(self):
        'Создаем таблицы, добавляем новые поля, и нужные индексы если их нет'
        logging.debug('Dbengine.check_and_add_addition')
        [self.conn.execute(query) for query in DB_SCHEMA]
        for k, v in addition_phone_fields.items():
            if self.conn.execute("SELECT COUNT(*) AS CNTREC FROM pragma_table_info('phones') WHERE name=?", [k]).fetchall()[0][0] == 0:
                self.conn.execute(f"ALTER TABLE phones ADD COLUMN {k} {v}")
                self.conn.execute(f"drop table if exists phones_delta")
        for sql in addition_queries:
            self.conn.execute(sql)
        for idx in addition_indexes:
            self.conn.execute(f"CREATE INDEX IF NOT EXISTS {idx}")
        self.conn.commit()

    def copy_data(self, path: str):
        'Копирует данные по запросам из другой БД sqlite, может быть полезно когда нужно объединить данные с нескольких источников'
        try:
            logging.debug(f'Open db {path}')
            if not os.path.exists(path):
                raise FileNotFoundError
            with sqlite3.connect(path) as src_conn:
                src_conn.row_factory = sqlite3.Row
                src_cur = src_conn.cursor()
                table = 'Phones'
                current_data = set(self.conn.execute('select distinct PhoneNumber,Operator,QueryDateTime from phones').fetchall())
                print(len(current_data))
                print("Copying Phones %s => %s" % (path, self.dbname))
                src_cur.execute('SELECT * FROM %s' % table)
                ins = None
                cnt_write, cnt_skip = 0, 0
                for row in src_cur.fetchall():
                    if not ins:
                        cols = tuple([k for k in row.keys() if k != 'id'])
                        ins = 'INSERT OR REPLACE INTO Phones %s VALUES (%s)' % (cols, ','.join(['?'] * len(cols)))
                    if (row['PhoneNumber'], row['Operator'], row['QueryDateTime']) in current_data:
                        cnt_skip += 1
                    else:
                        c = [row[c] for c in cols]
                        res = self.conn.execute(ins, c)
                        cnt_write += res.rowcount
            print(f'Update {cnt_write} row, skip {cnt_skip} row')
            self.conn.commit()
        except Exception:
            logging.info(f'Ошибка при копировании данных {store.exception_text()}')
            return False
        return True

class Mdbengine():
    def __init__(self, dbname=None):
        import pyodbc  # type: ignore
        if dbname is None:
            dbname = store.abspath_join(settings.mbplugin_ini_path, 'BalanceHistory.mdb')
        self.dbname = dbname
        DRV = '{Microsoft Access Driver (*.mdb)}'  # or 'Microsoft Access Driver (*.mdb, *.accdb)'
        DRVs = [el for el in pyodbc.drivers() if 'Access' in el and '*.mdb' in el]
        if len(DRVs) > 0:
            DRV = DRVs[0]
        else:
            logging.error(f'ODBC Microsoft Access Driver for mdb is not installed')
        self.conn = pyodbc.connect(f'DRIVER={DRV};DBQ={dbname}')
        # self.cur = self.conn.cursor()  # TODO it's wrong
        description = self.conn.execute('SELECT top 1 * FROM phones').description
        self.phoneheader = list(zip(*description))[0]
        phones_ini = store.ini('phones.ini').read()
        # phones - словарь key=MBphonenumber values=[phonenumber,region]
        self.phones = {v['Number']: (re.sub(r' #\d+', '', v['Number']), v['Region'])
                       for k, v in phones_ini.items() if k.isnumeric() and 'Monitor' in v}

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.conn.close()

    def to_sqlite(self, line):
        '''конвертирует строчку для sqlite:
        Убираем последовательный номер NN
        PhoneNumber -> MBphoneNumber (оригинал)
        PhoneNumber -> PhoneNumber (без добавки пробел#n)
        Оператор(region) из ini -> Operator
        return header, newline
        '''
        idxp = self.phoneheader.index('PhoneNumber')
        mbphoneNumber = line[idxp]
        s1, s2 = re.search(r'\A(.*?)( #\d+)?\Z', mbphoneNumber).groups()
        s2 = s2.strip() if s2 else '???'
        phonenumber, region = self.phones.get(mbphoneNumber, [s1, s2])
        header = self.phoneheader[1:] + ('MBphoneNumber', 'Operator')
        newline = [i for i in line]  # pyodbc.Row object has no attribute copy
        newline[idxp] = phonenumber
        newline = newline[1:] + [mbphoneNumber, region]
        return header, newline


def update_sqlite_from_mdb_core(dbname=None, deep=None) -> bool:
    'Обновляем данные из mdb в sqlite'
    if store.options('updatefrommdb') != '1':
        return False
    logging.info(f'Добавляем данные из mdb')
    if deep is None:
        deep = int(store.options('updatefrommdbdeep'))
    # читаем sqlite БД
    with Dbengine(fast=True) as db, Mdbengine(dbname) as mdb:  # BalanceHistory.mdb
        # Дата согласно указанному deep от которой сверяем данные
        dd = datetime.datetime.now() - datetime.timedelta(days=deep)
        logging.debug(f'Read from sqlite QueryDateTime>{dd}')
        sqldata = db.conn_execute_fetch("SELECT * FROM phones where QueryDateTime>?", [dd])
        dsqlite = {datetime.datetime.strptime(i[db.phoneheader.index('QueryDateTime')].split('.')[0], '%Y-%m-%d %H:%M:%S').timestamp(): i for i in sqldata}
        # теперь все то же самое из базы MDB
        logging.debug(f'Read from mdb QueryDateTime>{dd}')
        mdbcur = mdb.conn.execute("SELECT * FROM phones where QueryDateTime>?", [dd])
        mdbdata = mdbcur.fetchall()
        dmdb = {i[mdb.phoneheader.index('QueryDateTime')].timestamp(): i for i in mdbdata}
        logging.debug('calculate')
        # Строим общий список timestamp всех данных
        allt = sorted(set(list(dsqlite) + list(dmdb)))
        # обрабатываем и составляем пары данных которые затем будем подправлять
        pairs = []  # mdb timestamp, sqlite timestamp
        while allt:
            # берем одну строчку из общего списка
            c = allt.pop(0)
            # Если для этого timestamp есть строчка добавляем из
            pair = [c if c in dmdb else None, c if c in dsqlite else None]
            if allt == [] or allt[0] in dmdb and pair[0] is not None or allt[0] in dsqlite and pair[1] is not None:
                # Это следующая строка или была последняя
                pairs.append(pair)
            elif allt[0] in dmdb and pair[0] is None and allt[0] - c < 10:
                # следующий timestamp это пара MDB к записи sqlite ?
                pair[0] = allt.pop(0)
                pairs.append(pair)
            elif allt[0] in dsqlite and pair[1] is None and allt[0] - c < 10:
                # следующий timestamp это пара sqlite к записи mdb ?
                pair[1] = allt.pop(0)
                pairs.append(pair)
        logging.debug('Before:')
        logging.debug(f'Difference time:{len([1 for a,b in pairs if a!=b and a is not None and b is not None])}')
        logging.debug(f'Only mdb:{len([1 for a,b in pairs if b is None])}')
        logging.debug(f'Only sqlite:{len([1 for a,b in pairs if a is None])}')
        update_param = []
        insert_param, insert_header = [], []
        for num, [mdb_ts, sqlite_ts] in enumerate(pairs):
            if mdb_ts != sqlite_ts and mdb_ts is not None and sqlite_ts is not None:
                # исправляем время в sqlite чтобы совпадало с mdb
                update_param.append([datetime.datetime.fromtimestamp(mdb_ts), datetime.datetime.fromtimestamp(sqlite_ts)])
                pairs[num][1] = mdb_ts
            elif mdb_ts is not None and sqlite_ts is None:
                # Копируем несуществующие записи в sqlite из mdb
                header, line = mdb.to_sqlite(dmdb[mdb_ts])
                insert_param.append(line)
                insert_header = header
                pairs[num][1] = mdb_ts

        # есть что вставить ?
        logging.debug(f'Insert {len(insert_param)}')
        if insert_param:
            db.conn.executemany(f'insert into phones ({",".join(insert_header)}) VALUES ({",".join(list("?"*len(insert_header)))})', insert_param)
            db.conn.commit()

        # есть что проапдейтить ?
        logging.debug(f'Update {len(update_param)}')
        if update_param:
            db.conn.executemany('update phones set QueryDateTime=? where QueryDateTime=?', update_param)
            db.conn.commit()

        # дополнительные фиксы (у меня в mdb мусор оказался, чтобы не трогать mdb чистим здесь)
        for sql in addition_queries:
            db.conn.execute(sql)
            db.conn.commit()
        # прописываем колонку mbnumber
        update_mbnumber = [[MBphonenumber, phonenumber, region] for MBphonenumber, (phonenumber, region) in mdb.phones.items()]
        cur = db.conn.executemany(f'update phones set MBPhonenumber=? where MBPhonenumber is null and Phonenumber=? and operator=?', update_mbnumber)
        logging.debug(f'Update empty MBPhonenumber {cur.rowcount}:')
        db.conn.commit()

        logging.debug(f'After:')
        logging.debug(f'Difference time:{len([1 for a,b in pairs if a!=b and a is not None and b is not None])}')
        logging.debug(f'Only mdb:{len([1 for a,b in pairs if b is None])}')
        logging.debug(f'Only sqlite:{len([1 for a,b in pairs if a is None])}')
        logging.debug(f'Update complete')
    return True


def update_sqlite_from_mdb(dbname=None, deep=None) -> bool:
    'Обновляем данные из mbd True - success'
    try:
        return update_sqlite_from_mdb_core(dbname, deep)
    except Exception:
        logging.error(f'Ошибка при переносе данных из mdb в sqlite {store.exception_text()}')
        return False


def write_result_to_db(plugin, login, result):
    'пишем в базу если в ini установлен sqlitestore=1'
    try:
        if store.options('sqlitestore') == '1':
            with Dbengine() as db:
                logging.info(f'Пишем в базу {db.dbname}')
                db.write_result(plugin, login, result)
    except AttributeError:
        logging.info(f'Отсутствуют параметры {store.exception_text()} дополнительные действия не производятся')
    except Exception:
        logging.error(f'Ошибка при записи в БД {store.exception_text()}')


def flags(cmd, key=None, value=None):
    '''Работаем с флагами (таблица Flags) если в ini установлен sqlitestore=1, если нет просто вернем None
    cmd: set/setunic/get/delete/getall/deleteall
    value:
    start - запрос стартовал (start уникальный - больше одного быть не может)
    queue - запрос в очереди
    error - по запросу прошла ошибка
    '''
    try:
        if store.options('sqlitestore') == '1':
            logging.debug(f'Flag:{cmd}')
            with Dbengine() as db:
                if cmd.lower() == 'set':
                    db.conn.execute('REPLACE INTO flags(key,value) VALUES(?,?)', [key, value])
                    db.conn.commit()
                if cmd.lower() == 'setunic':
                    db.conn.execute('delete from flags where value=?', [value])
                    db.conn.commit()
                    db.conn.execute('REPLACE INTO flags(key,value) VALUES(?,?)', [key, value])
                    db.conn.commit()
                elif cmd.lower() == 'get':
                    qres = db.conn_execute_fetch('select value from flags where key=?', [key])
                    if len(qres) > 0:
                        return qres[0][0]
                elif cmd.lower() == 'getall':
                    qres = db.conn_execute_fetch('select * from flags')
                    return {k: v for k, v in qres}
                elif cmd.lower() == 'deleteall':
                    db.conn.execute('delete from flags')
                    db.conn.commit()
                elif cmd.lower() == 'delete':
                    db.conn.execute('delete from flags where key=?', [key])
                    db.conn.commit()
        else:
            if cmd.lower() == 'getall':
                return {}
    except Exception:
        logging.error(f'Ошибка при записи в БД {store.exception_text()}')


def responses() -> typing.Dict[str, str]:
    'Возвращаем все responses словарем, ключ - плагин_номер значение - json ответа'
    try:
        if store.options('sqlitestore') == '1':
            logging.debug(f'Responses from sqlite')
            db = Dbengine()
            qres = db.conn_execute_fetch('select key,value from responses')
            return {k: v for k, v in qres}
        else:
            return {}
    except Exception:
        logging.error(f'Ошибка при записи в БД {store.exception_text()}')
        return {}


if __name__ == '__main__':
    print('This is module dbengine')
    store.switch_to_mb_mode()
    if 'update_sqlite_from_mdb_all' in sys.argv:
        store.turn_logging(logginglevel=logging.DEBUG)
        update_sqlite_from_mdb(deep=10000)
