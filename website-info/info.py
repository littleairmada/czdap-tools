#!/usr/bin/env python
# -*- coding:utf-8
import json, sys, re, datetime, mechanize, cookielib, HTMLParser

class czdsException(Exception):
    pass

class czdsWebsite(object):
    ignore_tlds = [ 'TEST', 'test2' ]

    open_tlds_re = re.compile("""<div class="form-item form-type-checkbox form-item-tlds-fieldset-tld-.+?">\s*<input(.+?)/>\s*<label.+?>(.+?)\s*<""", re.DOTALL)
    open_tld_ipt_name_re = re.compile('name="([^"]+)"')
    open_tld_ipt_class_re = re.compile('class="([^"]+)"')
    request_table_re = re.compile("""<table.+?class=".*?my-requests[^"]*">(.+?)<\/table>""", re.DOTALL)
    table_tr_re = re.compile("""<tr[^>]*>(.+?)</tr>""", re.DOTALL)
    table_td_re = re.compile("""<td[^>]*>\s*(.*?)\s*</td>""", re.DOTALL | re.M)
    a_re = re.compile("""<a.+?href=["|'](.+?)["|'][^>]*>(.+?)</a>""", re.DOTALL)
    pager_last_page_re = re.compile("""<ul class="pager">.+?<li class="pager-current last">.+?<\/ul>""", re.DOTALL)
    request_info_re = re.compile("""<div class="title-request"[^>]*>(.+?):<\/div>.+?<div class="field-request"[^>]*>(.+?)<\/div>""", re.DOTALL)
    request_info_history_re = re.compile("""history-request">.+?<table[^>]+>(.+?)<\/table>""", re.DOTALL)

    def __init__(self):
        """ Create mechanize browser instance
        """
        self.br = mechanize.Browser()
        """ Create Cookie jar
        """
        self.cj = cookielib.LWPCookieJar()
        self.br.set_cookiejar(self.cj)

        """ Browser options
        """
        self.br.set_handle_equiv(True)
        self.br.set_handle_gzip(False)
        self.br.set_handle_redirect(True)
        self.br.set_handle_referer(True)
        self.br.set_handle_robots(False)

        """ Follows refresh 0 but not hangs on refresh > 0
        """
        self.br.set_handle_refresh(mechanize._http.HTTPRefreshProcessor(), max_time=1)

        """ Want debugging messages?
        """
        self.br.set_debug_http(False)
        self.br.set_debug_redirects(False)
        self.br.set_debug_responses(False)

        """ User-Agent (this is cheating, ok?)
        """
        self.br.addheaders = [('User-agent', 'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.0.1) Gecko/2008071615 Fedora/3.0.1-1.fc9 Firefox/3.0.1')]
        self.body = None
        self.__login = False

    def __del__(self):
        """ do auto-logout on object destruction
        """
        if self.__login and self.br:
            self.logout()

    """ remove all HTML tags from given string
    """
    @staticmethod
    def remove_tags(text):
        h = HTMLParser.HTMLParser()
        TAG_RE = re.compile(r'<[^>]+>')
        return h.unescape(TAG_RE.sub('', text))

    """ read given json config file
    """
    def readConfig(self, configFilename = 'config.json'):
        try:
            self.conf = json.load(open(configFilename))
        except:
            raise czdsException("Error loading '" + configFilename + "' file.")

    """ login on CZDS page
    """
    def login(self):
        self.br.open('https://czds.icann.org/')
        self.br.select_form(nr=0)
        self.br["name"] = self.conf['username']
        self.br["pass"] = self.conf['password']
        res = self.br.submit()
        self.body = res.read()
        if '<li class="first leaf"><a href="/en">Login</a></li>' in self.body :
            raise czdsException("Login failed!")
        self.__login = True

    """ do logout by simply calling logout page
    """
    def logout(self):
        self.br.open('https://czds.icann.org/en/user/logout')

    """ fetch all requests stats on dashboard
    """
    def requestStats(self, page = 0):
        res = self.br.open('https://czds.icann.org/en/dashboard?page=' + str(page))
        self.body = res.read()
        tableMatch = self.request_table_re.search(self.body)
        if not tableMatch:
            raise czdsException("Request Table not found!")

        data = []
        table = tableMatch.group(1)
        for row in self.table_tr_re.findall(table):
            cols = self.table_td_re.findall(row)
            if not cols:
                continue

            (lnk, zone) = self.a_re.search(cols[0]).groups()
            if zone in self.ignore_tlds:
                continue

            request_id = re.search('request/(\d+)', lnk).group(1)
            request_date = datetime.datetime.strptime(cols[1], "%d %B %Y")
            data.append({
                'id': request_id,
                'date': request_date,
                'zone': zone.strip().lower(),
                'status': cols[2]
            })
        lastPage = False
        if self.pager_last_page_re.search(self.body):
            lastPage = True

        return (data, lastPage)

    """ fetch details on request
    """
    def fetchRequestDetails(self, request_id):
        res = self.br.open('https://czds.icann.org/en/request/' + str(request_id))
        self.body = res.read()
        data = {}
        for kv in self.request_info_re.findall(self.body):
            (ky, vl) = kv
            if 'IP address' in ky:
                ips = []
                for ip in vl.split('<br/>'):
                    ip = self.remove_tags(ip)
                    if ip:
                        ips.append(ip)
                vl = ips
            elif 'Expires' in ky:
                vl = datetime.datetime.strptime(vl, "%d %B %Y, %H:%M:%S %Z")
            else:
                vl = self.remove_tags(vl).strip()

            data[ky.strip().lower()] = vl

        tableMatch = self.request_info_history_re.search(self.body)
        if not tableMatch:
            raise czdsException("History Table not found!")

        data['history'] = []
        table = tableMatch.group(1)
        for row in self.table_tr_re.findall(table):
            cols = self.table_td_re.findall(row)
            if not cols:
                continue

            history_date = datetime.datetime.strptime(cols[0], "%d %B %Y, %H:%M:%S %Z")
            data['history'].append({
                'date': history_date,
                'user': cols[1].strip(),
                'action': self.remove_tags(cols[2]).strip(),
                'response':  self.remove_tags(cols[3]).strip()
            })

        return data

    """ get list of current status of all zones
    """
    def checkOpenReq(self):
        res = self.br.open('https://czds.icann.org/en/request/add')
        self.body = res.read()
        data = {
        }
        for option in self.open_tlds_re.findall(self.body):
            (ipt, tld) = option
            if tld in self.ignore_tlds or tld == 'All TLDs':
                continue
            (name, ) = self.open_tld_ipt_name_re.findall(ipt)
            (cls, ) = self.open_tld_ipt_class_re.findall(ipt)

            ky = cls.replace('form-checkbox', '').strip()
            if ky == '' :
                ky = 'open'
            if not ky in data:
                data[ky] = []
            data[ky].append((name, tld))

        return data

    """ print current requests
    """
    def printData(self, data):
        for ky in ['open', 'expired', 'approved', 'pending']:
            if ky in data :
                print ky + ':'
                for item in data[ky]:
                    print ' ', item[1]

if __name__ == "__main__":
    try:
        ws = czdsWebsite()
        ws.readConfig()
        ws.login()
        data = ws.checkOpenReq()
        ws.printData(data)
    except Exception, e:
        sys.stderr.write("Error occoured: " + str(e) + "\n")
        exit(1)
