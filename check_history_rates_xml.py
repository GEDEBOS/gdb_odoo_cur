#!/usr/bin/python
# -*- encoding: utf-8 -*-
# 23/05/2014 - JB1 adaptation pour l'importation des taux historiques de la confédération

import os
import xmlrpclib
import time
import datetime
import mechanize
import re
from BeautifulSoup import BeautifulSoup
import ConfigParser

from optparse import OptionParser
parser = OptionParser()
parser.add_option("-d", "--db", dest="db", help="Nom de la base ")
parser.add_option("-U", "--user", dest="user", default='admin', help="User Odoo")
parser.add_option("-W", "--passwd", dest="passwd", help="mot de passe Odoo ")
parser.add_option("-H", "--host", dest="host", default='localhost', help="Adresse  Serveur")
parser.add_option("-p", "--port", dest="port", default='8069', help="port du serveur")
parser.add_option("-P", "--protocole", dest="protocole", default='http', help="protocole http/https")
parser.add_option("-S", "--start", dest="yearfrom", help="start year yyyy")

(options, args) = parser.parse_args()
user = options.user
pwd = options.passwd
base = options.db
host = options.host
port = options.port
proto = options.protocole
yearfrom = options.yearfrom

newrates = False
curdir = os.getcwd()


iniFile = curdir + '/check_all_rates.ini'
config = ConfigParser.ConfigParser()
config.read(iniFile)

rateurl = config.get('rates', 'url')

mois = ['', 'janvier', 'f&eacute;vrier', 'mars', 'avril', 'mai', 'juin', 'juillet', 'ao&ucirc;t', 'septembre',
        'octobre', 'novembre', 'd&eacute;cembre']


def create_daily_rates(id, values, terp_base, sock, uid, pwd):
    global newrates
    if 'currency' in values:
        currency = values.pop('currency')
    rows = sock.execute(terp_base, uid, pwd, 'res.currency.rate', 'search', [('currency_id', '=', id),
                                                                             ('name', '=', values['name'])])
    if not rows:
        newrates = True
        print "INF, new rate for currency %s quote %s admin_rate %s admin_coeff %s" % (currency, round(values['rate'],
                                                                                                       6),
                                                                                       values['rate_admin'],
                                                                                       values['rate_coeff'])
        res = sock.execute(terp_base, uid, pwd, 'res.currency.rate', 'create', values)
    else:
        dateobj = sock.execute(terp_base, uid, pwd, 'res.currency.rate', 'read', rows[0])
        if round(values['rate'], 6) != round(dateobj['rate'], 6) or values['rate_admin'] != dateobj['rate_admin']:
            newrates = True
            print "INF, update rate for currency %s quote %s admin_rate %s admin_coeff %s" % (dateobj['currency_id'][1],
                                                                                              round(values['rate'], 6),
                                                                                              values['rate_admin'],
                                                                                              values['rate_coeff'])
            res = sock.execute(terp_base, uid, pwd, 'res.currency.rate', 'write', dateobj['id'], values)
    return


def get_float(tocheck):
    try:
        number = float(tocheck)
    except:
        number = float(re.findall("[0-9.]*[0-9]+", str(tocheck))[0])
    return number


def parse_page(html):
    webrates = {}
    ncont = BeautifulSoup(html)
    ntabl = ncont.find("table")
    kur = 0
    for row in ntabl.findAll('tr'):
        col = row.findAll('td')
        if len(col) == 1 and kur == 0:  # titel
            months = ['Januar', 'Februar', 'Mârz', 'April', 'May', 'Juni', 'July', 'August', 'September', 'Oktober',
                      'November', 'Dezember']
            date = col[0].contents[0]
            date = date[date.find('('):].replace('(', '').replace(')', '').split(' ')
            month = date[2]
            year = date[3]        
            
        if len(col) == 3:
            kur += 1
            if kur > 1:
                code = col[1].contents[0].split(' ')
                if len(code) == 2:
                    base = int(code[0])
                    curr = code[1]
                    rate = get_float(col[2].contents[0])
                    if rate != 0:
                        currency = {'base': base, 'rate': rate, 'converted': base / rate}
                    else:
                        currency = {'base': base, 'rate': rate, 'converted': 0}
                    webrates[curr] = currency
    return webrates   


def other_base(webrates, base):
    newrates = {}
    for key, value in webrates.iteritems():
        if key == base:
            newrates[base] = 1
            baserate = 1 / value['converted']
            break
    for key, value in webrates.iteritems():
        if key != base:
            currency = {'base': value['base'], 'rate': value['rate'], 'converted': baserate * value['converted']}
        else:
            currency = {'base': value['base'], 'rate': value['rate']}
        newrates[key] = currency
    newrates['CHF'] = {'base': 1, 'rate': 1, 'converted': baserate}
    return newrates


def update_base(base, uid, pwd, webrates, daterate):
    company_ids = sock.execute(base,uid,pwd,'res.company','search',[('name','>','')])

    if company_ids:     
        curobj = sock.execute(base,uid,pwd,'res.company','read',company_ids[0],['currency_id'])
        base_currency = curobj['currency_id'][1].upper()
    else:
        base_currency = 'CHF'
    if base_currency <> 'CHF':
        convrates = other_base(webrates,base_currency)
    else:
        convrates = webrates

    ids = sock.execute(base,uid,pwd,'res.currency','search',[('name','>','')])   

    for id in ids:
        objcur =  sock.execute(base,uid,pwd,'res.currency','read',id)
        values = {'name': daterate, 'currency_id': objcur['name'], 'currency': objcur['name']}
        currency = objcur['name']
        if currency != base_currency:
            try:
                quote = convrates[currency]['converted']
                rate_admin = convrates[currency]['rate']
                rate_coeff = convrates[currency]['base']
            except:
                print "ERR, missing currency", currency
                madate = time.strftime('%Y-%m-%d %H:%M')
                continue
            values['rate'] = quote
            values['rate_admin'] = rate_admin
            values['rate_coeff'] = rate_coeff
        else:
            values['rate'] = 1
            if currency != 'CHF':
                values['rate_admin'] = convrates[currency]['rate']
            else:
                values['rate_admin'] = 1
            values['rate_coeff'] = 1
        create_daily_rates(id, values, base, sock, uid, pwd)

url = proto + '://' + host + ':' + port
server = xmlrpclib.ServerProxy(url + '/xmlrpc/common')
uid = server.login(base,user, pwd)
if not uid:
    print "ERR, invalid login to database %s for %s" % (base, user)
    exit(0)

sock = xmlrpclib.ServerProxy(url + '/xmlrpc/object')

curyear = datetime.datetime.now().strftime("%Y")
curmonth = datetime.datetime.now().strftime("%m")
jahr = yearfrom
year = int(yearfrom)
while year <= int(curyear):
    for monat in range (1,13):
        print "INF processing year", year, "month", monat
        br = mechanize.Browser()
        br.set_handle_equiv(True)
        #br.set_handle_gzip(True)
        br.set_handle_redirect(True)
        br.set_handle_referer(True)
        br.set_handle_robots(False)
        br.set_handle_refresh(mechanize._http.HTTPRefreshProcessor(), max_time = 1)
        br.addheaders = [('User-agent',
                          'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.0.1) Fedora/3.0.1-1.fc9 Firefox/3.0.1')]
        br.open(rateurl)
        br.select_form(nr = 0)
        br.form['monat'] = [str(monat)]
        br.form['jahr'] = str(year)
        br.submit()
        html = br.response().read()
        webrates = parse_page(html)
        daterate = '%s-%s-01' % (str(year), str(monat))
        update_base(base, uid, pwd, webrates, daterate)
        if year == int(curyear) and monat == int(curmonth):
            break        
    year += 1
print "INF done"
