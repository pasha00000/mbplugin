#!/usr/bin/python3
# -*- coding: utf8 -*-
import logging, os, sys, re, traceback, asyncio
import store, settings
import pyppeteeradd as pa

interUnit = 'GB'  # В каких единицах идет выдача по интернету

icon = '789C75524D4F5341143D84B6A8C0EB2BAD856A4B0BE5E301A508A9F8158DC18498A889896E8C3B638C31F147B83171E34E4388AE5C68E246A3C68D0B5DA82180B5B40A5A94B6F651DA423F012D2DE09D79CF4A207DC949A733F79C39F7CC1D3A37A801FF060912415451058772A09E6FFD04CD18F4DA09C267C214210051FB857EFFC1AFEEB3F3495E2F68DEA35EF396F086F6BCBC46D47E257C2304A1D7045157350DA13A80FA6A1F6AAB7CB4F6AB5A5E08DA71D2F840FC772AEF3B44DD0F1874215A87D1DA34871B57658CDE4F1212B87E2504BBD94F5A01D5938F7B16341F8937CB79C65DBF60DA2DC3E594F1FAE532D64B1BD8DCDCE428D1FAC5B30CDAAD33E483799C2E6B187411E245D124CC63BF18C3DD3BB9326F3B6EDF4A506FB3C49FE5BE99C6DE3D32F6E9636836C671A0631153DEB58AFCC9F155EA4DE951D40579CE8C6B37C5693F895347D388C9EB15F9D148119E1E190D3551F23DC7F366F73A2D4974DA52183E9E831CADCC0F878A38E88AC15C3B4F1A119E5D8B39814EEB125CAD199CF0E4C97FA9227F7CAC809E96382CE4D9489989BA9F7092EF2E7B8A7ACF62D0B58C278F8A15F90F4656D0D29880D5B0C07363EFD6665944B72385012947FC15DCBC56403EB7939BCD6CE0F2852CF193B0352C500F8C1F267EB2CC3FEC5EA10CFFE0D5F39D193C7D5C80BB2DCDEFDBCADFEEFF58FF2A2E9D2FC0F7E9BFC6C45809A74FE62035A778BDE23FCAFD3B28BF0EEB22E597E61E0EF52EE348DF2A2E9EFD8D87236B18BD57C099A13CE596E639B37AF6E66C5E597ECC0B7B7BA97909BDCE0CFA3BB3F074E73906A43CFADA73FC6DBAD4BB597D63DD3C0C35CA0C59049A3D933203926D89DFE3261D779B0217FD67DA2C273667AC9ECDBB323F33F80B823D9864'

class mts_over_puppeteer(pa.balance_over_puppeteer):
    async def async_main(self):
        mts_usedbyme = store.options('mts_usedbyme')
        await self.do_logon(
            url='https://login.mts.ru/amserver/UI/Login?service=newlk',  # - другая форма логина - там оба поля на одной странице, и можно запомнить сессию
            # url='https://lk.mts.ru/', # а на этой запомнить сессию нельзя
            user_selectors={
                'chk_lk_page_js': "document.querySelector('form input[id^=phone]')==null && document.querySelector('form input[id=password]')==null",
                # У нас форма из двух последовательных окон (хотя иногода бывает и одно, у МТС две разных формы логона)
                'chk_login_page_js': "document.querySelector('form input[id=phoneInput]')!=null || document.querySelector('form input[id=password]')!=null",
                'login_clear_js': "document.querySelector('form input[id^=phone]').value=''",
                'login_selector': 'form input[id^=phone]', 
                # проверка нужен ли submit после логина (если поле пароля уже есть то не нужен, иначе нужен)
                'chk_submit_after_login_js': "document.querySelector('form input[id=phoneInput]')!=null || document.querySelector('form input[id=password]')==null",  
                'remember_checker': "document.querySelector('form input[name=rememberme]')!=null && document.querySelector('form input[name=rememberme]').checked==false",  # Проверка что флаг remember me не выставлен
                'remember_js': "document.querySelector('form input[name=rememberme]').click()",  # js для выставления remember me
                })
        # TODO close banner # document.querySelectorAll('div[class=popup__close]').forEach(s=>s.click())
        if self.login_ori != self.login:  # это финт для захода через другой номер 
            # если заход через другой номер то переключаемся на нужный номер
            # TODO возможно с прошлого раза может сохраниться переключенный но вроде работает и так
            await self.page_waitForSelector("[id=ng-header__account-phone_desktop]")
            self.responses = {}  # Сбрасываем все загруженные данные - там данные по материнскому телефону                
            url_redirect = f'https://login.mts.ru/amserver/UI/Login?service=idp2idp&IDButton=switch&IDToken1=id={self.acc_num},ou=user,o=users,ou=services,dc=amroot&org=/users&ForceAuth=true&goto=https://lk.mts.ru'
            await self.page_goto(url_redirect)
            # !!! Раньше я на каждой странице при таком заходе проверял что номер тот, сейчас проверяю только на старте
            await self.page_waitForNavigation()
            numb = await self.page_evaluate("document.getElementById('ng-header__account-phone_desktop').innerText")
            if numb is None:
                return  # номера на странице нет - уходим
            logging.info(f'PHONE {numb}')
            if re.sub(r'(?:\+7|\D)', '', numb) != self.acc_num:
                return  # Если номер не наш - уходим            

        # Для начала только баланс быстрым способом (может запаздывать)
        await self.wait_params(params=[
            {'name': 'Balance', 'url_tag': ['api/login/userInfo'], 'jsformula': "parseFloat(data.userProfile.balance).toFixed(2)"},
            # Закрываем банеры (для эстетики)
            {'name': '#banner1', 'url_tag': ['api/login/userInfo'], 'jsformula': "document.querySelectorAll('mts-dialog div[class=popup__close]').forEach(s=>s.click())", 'wait':False},
            ])

        # Потом все остальное
        res1 = await self.wait_params(params=[
            {'name': 'TarifPlan', 'url_tag': ['api/login/userInfo'], 'jsformula': "data.userProfile.tariff"},
            {'name': 'UserName', 'url_tag': ['api/login/userInfo'], 'jsformula': "data.userProfile.displayName"},
            {'name': 'Balance', 'url_tag': ['for=api/accountInfo/mscpBalance'], 'jsformula': "parseFloat(data.data.amount).toFixed(2)"},
            {'name': '#counters', 'url_tag': ['for=api/sharing/counters'], 'jsformula': "data.data.counters"},
            ])
        if '#counters' in res1 and type(res1['#counters']) == list and len(res1['#counters'])>0:
            counters = res1['#counters']
            # Минуты
            calling = [i for i in counters if i['packageType'] == 'Calling']
            if calling != []:
                unit = {'Second': 60, 'Minute': 1}.get(calling[0]['unitType'], 1)
                nonused = [i['amount'] for i in calling[0] ['parts'] if i['partType'] == 'NonUsed']
                usedbyme = [i['amount'] for i in calling[0] ['parts'] if i['partType'] == 'UsedByMe']
                if nonused != []:
                    self.result['Min'] = int(nonused[0]/unit)
                if usedbyme != []:
                    self.result['SpendMin'] = int(usedbyme[0]/unit)
            # SMS
            messaging = [i for i in counters if i['packageType'] == 'Messaging']
            if messaging != []:
                nonused = [i['amount'] for i in messaging[0] ['parts'] if i['partType'] == 'NonUsed']
                usedbyme = [i['amount'] for i in messaging[0] ['parts'] if i['partType'] == 'UsedByMe']
                if (mts_usedbyme == '0' or self.login not in mts_usedbyme.split(',')) and nonused != []:
                    self.result['SMS'] = int(nonused[0])
                if (mts_usedbyme == '1' or self.login in mts_usedbyme.split(',')) and usedbyme != []:
                    self.result['SMS'] = int(usedbyme[0])
            # Интернет
            internet = [i for i in counters if i['packageType'] == 'Internet']
            if internet != []:
                unitMult = settings.UNIT.get(internet[0]['unitType'], 1)
                unitDiv = settings.UNIT.get(interUnit, 1)
                nonused = [i['amount'] for i in internet[0] ['parts'] if i['partType'] == 'NonUsed']
                usedbyme = [i['amount'] for i in internet[0] ['parts'] if i['partType'] == 'UsedByMe']
                if (mts_usedbyme == '0' or self.login not in mts_usedbyme.split(',')) and nonused != []:
                    self.result['Internet'] = round(nonused[0]*unitMult/unitDiv, 2)
                if (mts_usedbyme == '1' or self.login in mts_usedbyme.split(',')) and usedbyme != []:
                    self.result['Internet'] = round(usedbyme[0]*unitMult/unitDiv, 2)
                            
        await self.page_goto('https://lk.mts.ru/uslugi/podklyuchennye')
        res2 = await self.wait_params(params=[
            {'name': '#services', 'url_tag': ['for=api/services/list/active$'], 'jsformula': "data.data.services.map(s=>[s.name,!!s.subscriptionFee.value?s.subscriptionFee.value:0])"}])
        try:
            services = sorted(res2['#services'], key=lambda i:(-i[1],i[0]))
            free = len([a for a,b in services if b==0 and (a,b)!=('Ежемесячная плата за тариф', 0)])
            paid = len([a for a,b in services if b!=0])
            paid_sum = round(sum([b for a,b in services if b!=0]),2)
            self.result['UslugiOn'] = f'{free}/{paid}({paid_sum})'
            self.result['UslugiList'] = '\n'.join([f'{a}\t{b}' for a, b in services])
        except Exception:
            logging.info(f'Ошибка при получении списка услуг {"".join(traceback.format_exception(*sys.exc_info()))}')

def get_balance(login, password, storename=None):
    ''' На вход логин и пароль, на выходе словарь с результатами '''
    return mts_over_puppeteer(login, password, storename).main()

if __name__ == '__main__':
    print('This is module mts on puppeteer (mts)')
