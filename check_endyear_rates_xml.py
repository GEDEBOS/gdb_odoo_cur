#!/usr/bin/python
# -*- encoding: utf-8 -*-
# 23/05/2014 JB1 adaptation pour chargement des taux de de fin d'année de la confédération

import os
import xmlrpclib
import ConfigParser

import re
from BeautifulSoup import BeautifulSoup as Soup

from optparse import OptionParser
parser = OptionParser()
parser.add_option("-d", "--db", dest="db", default='salvia', help="Nom de la base ")
parser.add_option("-U", "--user", dest="user", default='admin', help="User Odoo")
parser.add_option("-W", "--passwd", dest="passwd", help="mot de passe Odoo ")
parser.add_option("-H", "--host", dest="host", default='localhost', help="Adresse  Serveur")
parser.add_option("-p", "--port", dest="port", default='8069', help="port du serveur")
parser.add_option("-P", "--protocole", dest="protocole", default='http', help="protocole http/https")
parser.add_option("-f", "--file", dest="filename", help="xml file to import")

(options, args) = parser.parse_args()
user = options.user
pwd = options.passwd
base = options.db
host = options.host
port = options.port
proto = options.protocole
filename = options.filename

newrates = False
curdir = os.getcwd()

mois = ['', 'janvier', 'f&eacute;vrier', 'mars', 'avril', 'mai', 'juin', 'juillet', 'ao&ucirc;t', 'septembre',
        'octobre', 'novembre', 'd&eacute;cembre']


def create_daily_rates(curid, values, terp_base, sock, uid, pwd):
    global newrates
    if 'currency' in values:
        currency = values.pop('currency')
    rows = sock.execute(terp_base, uid, pwd, 'res.currency.rate', 'search', [('currency_id', '=', curid),
                                                                             ('name', '=', values['name'])])
    if not rows:
        newrates = True
        print "INF, new rate for currency %s quote %s admin_rate %s admin_coeff %s" % (currency,
                                                                                       round(values['rate'], 6),
                                                                                       values['rate_admin'],
                                                                                       values['rate_coeff'])
        res = sock.execute(terp_base, uid, pwd, 'res.currency.rate', 'create', values)
    else:
        dateobj = sock.execute(terp_base, uid, pwd, 'res.currency.rate', 'read', rows[0])
        if round(values['rate'], 6) != round(dateobj['rate'], 6) or values['rate_admin'] != dateobj['rate_admin']:
            newrates = True
            print "INF, update rate for currency %s quote %s admin_rate %s admin_coeff %s" % \
                  (dateobj['currency_id'][1], round(values['rate'], 6), values['rate_admin'], values['rate_coeff'])
            res = sock.execute(terp_base, uid, pwd, 'res.currency.rate', 'write', dateobj['id'], values)
    return


def get_float(tocheck):
    try:
        number = float(tocheck)
    except:
        number = float(re.findall("[0-9.]*[0-9]+", str(tocheck))[0])
    return number


def other_base(webrates, base):
    newrates = {}
    for key, value in webrates.iteritems():
        if key.lower() == base:
            newrates[base] = 1
            baserate = 1 / value['converted']
            break
    for key, value in webrates.iteritems():
        print "key,value", key, value
        if key.lower() != base:
            currency = {'base': value['base'], 'rate': value['rate'], 'converted': baserate * value['converted']}
        else:
            currency = {'base': value['base'], 'rate': value['rate']}
        newrates[key] = currency
    newrates['CHF'] = {'base': 1, 'rate': 1, 'converted': baserate}
    return newrates


def update_base(base, uid, pwd, webrates, daterate):
    company_ids = sock.execute(base, uid, pwd, 'res.company', 'search', [('name', '>', '')])
    if company_ids:     
        curobj = sock.execute(base, uid, pwd, 'res.company', 'read', company_ids[0], ['currency_id'])
        base_currency = curobj['currency_id'][1].lower()
    else:
        base_currency = 'chf'
    if base_currency != 'chf':
        convrates = other_base(webrates, base_currency)
    else:
        convrates = webrates
    
    ids = sock.execute(base, uid, pwd, 'res.currency', 'search', [('name', '>', '')])

    for curid in ids:
        objcur = sock.execute(base, uid, pwd, 'res.currency', 'read', curid)
        values = {'name': daterate, 'currency_id': objcur['id'], 'currency': objcur['name']}
        currency = objcur['name']
        if currency.lower() != base_currency:
            try:
                quote = convrates[currency]['converted']
                rate_admin = convrates[currency]['rate']
                rate_coeff = convrates[currency]['base']
            except:
                print "ERR, missing currency", currency
                continue
            values['rate'] = quote
            values['rate_admin'] = rate_admin
            values['rate_coeff'] = rate_coeff
        else:
            values['rate'] = 1
            if currency in convrates:
                values['rate_admin'] = convrates[currency]['rate']
            else:
                values['rate_admin'] = 1
            values['rate_coeff'] = 1
        print "DBG rate", values['rate'], 'rate admin', values['rate_admin'], "coeff", values['rate_coeff']
        create_daily_rates(curid, values, base, sock, uid, pwd)

url = proto + '://' + host + ':' + port
server = xmlrpclib.ServerProxy(url + '/xmlrpc/common')
uid = server.login(base, user, pwd)
if not uid:
    print "ERR, invalid login to database %s for %s" % (base, user)
    exit(0)
sock = xmlrpclib.ServerProxy(url + '/xmlrpc/object')


def parseXML(filename):
    print "INF parsing XML (big file)..."
    webrates = {}    
    xmldoc = Soup(open(filename).read())
    #print xmldoc.prettify()
    print "INF processing end year rates..."
    fnd = 0
    for rate in xmldoc.findAll('exchangerateyearend'):
        if fnd == 0:
            print "INF found rates... processing"
        fnd += 1
        rate_element = dict(rate.attrs)
        curr = rate_element['currency']
        if 'denomination' in rate_element:
            base = int(rate_element['denomination'])
        else:
            base = 1
        rate = get_float(rate_element['value'])
        year = rate_element['year']
        currency = {'base': base, 'rate': rate, 'converted': base / rate}
        webrates[curr] = currency
    print "INF processed XML..."
    if fnd > 0:
        return webrates, year
    else:
        return False, False
    
(webrates, year) = parseXML(filename)
if webrates and year:
    daterate = '%s-12-31' % year    
    update_base(base, uid, pwd, webrates, daterate)
print "INF done"
