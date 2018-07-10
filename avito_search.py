#!/usr/bin/env python
# -*- coding: cp1251 -*-
from urllib.request import urlopen
from urllib.request import Request
from urllib.request import urlretrieve
from bs4 import BeautifulSoup
import webbrowser
import tempfile
import os
import time
import pickle
from datetime import datetime
from datetime import timedelta
from datetime import date 
from colorama import Fore, init, Style

minPrice = 32000
maxPrice = 50000
query = 'macbook+pro+13'

redPrice = 44500
greenPrice = 40000

dataFileNameDef = 'avito_apple.data'
avitoBase = 'https://www.avito.ru'
avitoRequestPattern = '/moskva/noutbuki?p={}&pmax={}&pmin={}&user=1&bt=1&q={}'

youlaBase = "https://youla.ru"
youlaRequestPattern = "/moskva/kompyutery/noutbuki?attributes[notebook_brand][0]=9241&attributes[notebook_diagonal_ekrana][0]=9259&attributes[notebook_tip][0]=9236&attributes[price][from]={}00&attributes[price][to]={}00&q={}"
youlaRequest = youlaBase + youlaRequestPattern

pages = 10
timeout = 1.5

def parsePrice(price):
   if price is None or not price or price == 0:
      return 0
   return int(price.replace(' ', '')[:-1])

def parseMonth(val):
   val = val.lower()
   if val == 'января':
      month = 1
   elif val == 'февраля':
      month = 2
   elif val == 'марта':
      month = 3
   elif val == 'апреля':
      month = 4
   elif val == 'мая':
      month = 5
   elif val == 'июня':
      month = 6
   elif val == 'июля':
      month = 7
   elif val == 'августа':
      month = 8
   elif val == 'сентября':
      month = 9
   elif val == 'октября':
      month = 10
   elif val == 'ноября':
      month = 11
   elif val == 'декабря':
      month = 12
   else:
      print('Unknown month:', val)
      return 1
   return month

def parseDate(raw):
   day = timedelta(days=1)
   now = datetime.now()
   rawParts = raw.split()

   if len(rawParts) in [3, 1]:
      if rawParts[0] == 'сегодня':
         return now.date()
      if rawParts[0] == 'вчера':
         return now.date() - day

   if len(rawParts) in [4, 2]:
      day = int(rawParts[0])
      year = now.year
      month = parseMonth(rawParts[1])
   else:
      try:
         day = int(rawParts[0])
         year = now.year - 1
         month = parseMonth(rawParts[1])
      except Exception as e:
         return now.date()

   return date(year, month, day)

class Item:
   def __init__(self):
      self.id = 0
      self.link = ''
      self.title = ''
      self.text = ''
      self.price = 0
      self.oldPrice = 0
      self.retina = False
      self.ssd = False
      self.gb = 0
      self.ram = 0
      self.core = ''
      self.year_prefix = ''
      self.year = 0
      self.date = datetime.now().date()
      self.serial = ''
      self.cycles = ''
      self.comment = ''
      self.box = False
      self.banned = False
      self.source = 'a'
      self.deleted = False

   @staticmethod
   def parse(item):
      p = Item()
      for a in item.__dict__:
         if a.startswith('_'):
            continue
         if hasattr(p, a):
            setattr(p, a, getattr(item, a))
      return p

   def floatYear(self):
      xx = self.year
      if self.year_prefix == 'early':
         xx = xx + 0.1
      elif self.year_prefix == 'mid':
         xx = xx + 0.5
      elif self.year_prefix == 'late':
         xx = xx + 0.9
      return xx

   def floatCore(self):
      if self.core == 'i5':
         return 5;
      if self.core == 'i7':
         return 7;

   def days(self):
      return (datetime.now().date() - self.date).days

   def featured(self):
      return (self.year > 2012 or self.retina)

   def __str__(self):
      if not self.year_prefix and self.year == 0 and self.retina:
         self.year_prefix = '?'
         self.year = 2012

      features = ''
      #if self.year_prefix:
      features += '{: >5} '.format(self.year_prefix)
      #else:
      #   features += '      '.format(self.year_prefix)
      self.year = int(self.year)
      #if self.year > 0:
      features += '{: >4} '.format(self.year)
      #else:
      #   features += '     '.format(self.year)
      self.gb = int(self.gb)
      #if self.gb > 0:
      features += '{: >3} '.format(self.gb)
      #else:
      #   features += '    '.format(self.gb)
      self.ram = int(self.ram)
      #if self.ram > 0:
      features += '{: >3}'.format(self.ram)
      #else:
      #   features += '   '.format(self.ram)
      #if self.cycles:
      features += '| {: >4}'.format(self.cycles)
      #else:
      #   features += '|     '.format(self.cycles)
      if self.box:
         features += ' box '
      else:
         features += '     '
      priceDelta = self.oldPrice - self.price
      priceDelta = priceDelta if priceDelta > 0 else ''

      colorPrice = Fore.RESET
      color = Fore.RESET
      if self.price > redPrice:
         colorPrice = Fore.RED
      elif self.price < greenPrice:
         colorPrice = Fore.GREEN

      color = colorPrice
      if self.ram > 4 and self.gb > 200 and self.year > 2012:
         color = Fore.YELLOW

      if self.deleted or self.banned:
         colorPrice = Fore.BLUE
         color = Fore.BLUE

      return  (colorPrice + '{} {: >5}| ' + color + '{: >2} | {: >2} days | {} | {}' + Fore.RESET).format(self.price, priceDelta, features, self.days(), self.source, self.comment)

def hasAttr(a, d):
   return a in d.attrs

def hasClass(c, d):
   return hasAttr('class', d) and c in d['class']

def getByClass(className, s):
   return [d for d in s if hasClass(className, d)]

def getValueByClass(className, s, indx = 0):
   allValues = [d.get_text().strip() for d in s if hasClass(className, d)]
   return allValues[indx] if allValues else ''

def getAttrByClass(attr, className, s):
   allAttrs = [d.get(attr).strip() for d in s if (hasClass(className, d) and hasAttr(attr, d))]
   return allAttrs[0] if allAttrs else None

def matchIn(item, attr, values, postfix = ['']):
   text = item.text.lower().replace('2.4','').replace('2,4','')
   title = item.title.lower().replace('2.4','').replace('2,4','')
   for v in values:
      for pstf in postfix:
         sv = str(v).lower() + pstf.lower()
         if sv in text or sv in title:
            setattr(item, attr, v)
            return

def parseTitleAndDescription(item):
   item.retina = 'retina' in item.text.lower() or 'retina' in item.title.lower()
   item.ssd = 'ssd' in item.text.lower() or 'ssd' in item.title.lower()

   cores = ['i5', 'i7']
   matchIn(item, 'core', cores)
         
   rams = [4, 8, 16, 32]
   postfix = ['gb', ' gb', u'гб', u' гб', '/']
   matchIn(item, 'ram', rams, postfix)

   postfix = ['', '/']
   gbs = [120, 128, 256, 512]
   matchIn(item, 'gb', gbs, postfix)

   pfx = ['early', 'mid', 'late']
   matchIn(item, 'year_prefix', pfx)

   years = [2011, 2012, 2013, 2014, 2015, 2016, 2017]
   matchIn(item, 'year', years)

def parseAvitoItem(s):
   links = s.find_all('a')
   link = avitoBase + getAttrByClass('href', 'item-description-title-link', links)

   item = Item()
   item.source = 'a'

   allDivs = s.find_all('div')

   item.link = link
   item.price = parsePrice(getValueByClass('about', allDivs))
   item.title = getValueByClass('item-description-title-link', links)

   time.sleep(timeout)
   try:
      html = urlopen(item.link).read().decode('utf-8')
   except:
      return item
   soup = BeautifulSoup(html, 'html.parser')
   allDivs = soup.find_all('div')

   item.text = getValueByClass('item-description-text', allDivs)
   item.oldPrice = parsePrice(getValueByClass('item-price-old', allDivs))

   item.date = getValueByClass('title-info-metadata-item', allDivs)
   rawDate = item.date.split(' ')
   item.date = parseDate(' '.join(rawDate[3:]))
   item.id = int(rawDate[1][:-1])

   parseTitleAndDescription(item)

   return item

def parseYoulaItem(s):
   link = youlaBase + s.find('a').get('href')

   item = Item()
   item.source = 'y'

   req = Request(link)
   try:
      html = urlopen(req).read().decode('utf-8')
   except:
      return item
   soup = BeautifulSoup(html, 'html.parser')
   allDivs = soup.find_all('div')

   item.title = getValueByClass('product__title', soup.find_all('h1'))
   item.text = getValueByClass('product__text', allDivs)

   #if 'air' in item.title.lower() or 'air' in item.text.lower():
   #   return Item()

   item.id = link.split('-')[-1]
   item.link = link

   price = getValueByClass('product__price', allDivs)
   item.price = int(''.join(price.split()[:2]))
   item.oldPrice = 0

   rawDate = soup.find('time').get_text()
   item.date = parseDate(rawDate)

   parseTitleAndDescription(item)
   return item

def processAvito(minPrice, maxPrice):
   print('Collect from Avito in progress...')

   items = []
   page = 0
   for i in range(pages):
      page = i + 1
      avitoRequest = avitoRequestPattern.format(page, maxPrice, minPrice, query)
      req = Request(avitoBase + avitoRequest)

      try:
         html = urlopen(req).read().decode('utf-8')
         soup = BeautifulSoup(html, 'html.parser')
         allDivs = [d for d in soup.find_all('div') if ('class' in d.attrs and 'item_table' in d['class'])]
         if not allDivs:
            print('Banned due to suspicious activity')
            return

         for raw in allDivs:
            item = parseAvitoItem(raw)
            if not item.featured():
               print('.', end='', flush=True)
               continue
            items.append(item)
            print('+', end='', flush=True)
            time.sleep(timeout)
         print()
      except Exception as e:
         break
   return items

def processYoula(minPrice, maxPrice):
   print('Collect from Youla in progress...')

   req = Request(youlaRequest.format(minPrice, maxPrice, query))
   html = urlopen(req).read().decode('utf-8')
   soup = BeautifulSoup(html, 'html.parser')
   allDivs = [d for d in soup.find_all('li') if ('class' in d.attrs and 'product_item' in d['class'])]

   items = []
   for s in allDivs:
      item = parseYoulaItem(s)
      if item.featured():
         print('+', end='', flush=True)
         items.append(item)
      else:
         print('.', end='', flush=True)
      time.sleep(timeout)

   print()
   return items

def edit(item):
   print('=' * 20)
   print(item)
   print('=' * 20)

   attrs = []
   i = 0
   for a in item.__dict__:
      if not a.startswith('_'):
         print('{: >2}: {}: {}'.format(i, a, getattr(item, a)))
         attrs.append(a)
         i += 1

   print('=' * 20)
   print(' o: Open in browser'.format(i, a, getattr(item, a)))
   print(' q: Quit'.format(i, a, getattr(item, a)))

   print('Choice:', end='')
   c = input().lower()
   if c == 'q':
      return
   if c == 'o':
      webbrowser.open_new_tab(item.link)
      clear()
      item = edit(item)
      return item
   try:
      if int(c) not in range(i):
         clear()
         item = edit(item)
         return item
   except Exception as e:
      print(e)
      input()
      clear()
      item = edit(item)
      return item

   print('Changing "{}"'.format(attrs[int(c)]))
   print('New value:', end='');
   val = input()
   setattr(item, attrs[int(c.strip())], val)
   return item

def save(items):
   print('Save it? [y|N]:', end='');
   if input().lower() == 'y':
      fname = dataFileNameDef
      print('Saving to {}'.format(fname))
      with open(fname, 'wb') as f:
         pickle.dump(items, f)

def output(items, num = True):
   #items = [i for i in items if not i.banned]
   if num:
      i = 0
      for d in items:
         print('{: >2}: {}'.format(i, d))
         i += 1
   else:
      for d in items:
         print(d)

def restore(short):
   fname = dataFileNameDef
   dumped = []

   try:
      with open(fname, 'rb') as f:
         dumped = pickle.load(f)
   except:
      pass

   parsed = []
   for d in dumped:
      p = Item.parse(d)
      if short and (p.banned or p.deleted or p.year < 2013 or p.ram == 4):
         continue
      parsed.append(p)

   parsed.sort(key=lambda x: int(x.year) * 1000000 + int(x.gb) + int(x.ram) * (100 if int(x.ram) > 4 else 1), reverse=True)
   return parsed

def edit_dialog(dumped, c):
   #dumped = [i for i in dumped if not i.banned]
   clear()
   i = edit(dumped[c])
   if i is None:
      return False
   print(i)
   return True

def clear():
   os.system('cls' if os.name=='nt' else 'clear')

def menu():
   print('=' * 20)
   print('r: Run avito search')
   print('s: Short/full view switch')
   print('p: Preferences')
   print('d: Download data file')
   print('q: Quit')
   print('Choice: ', end='')
   c = input().lower()
   clear()
   print('=' * 20)
   return c

def merge(stored, loaded):
   removedCnt = 0
   restoredCnt = 0
   changedCnt = 0
   newCnt = 0
   result = []
   for s in stored:
      loaded_item = [l for l in loaded if l.id == s.id]
      if not loaded_item:
         if not s.deleted:
            s.comment = '[removed]' + s.comment
            s.deleted = True
            removedCnt += 1
         result.append(s)
         continue

      if s.deleted:
         s.comment = '[restored]' + s.comment
         restoredCnt += 1
         result.append(s)
         continue

      loaded_item = loaded_item[0]

      if (not s.price == loaded_item.price) or (not s.oldPrice == loaded_item.oldPrice):
         s.comment += '[changed] {}->{}'.format(s.price, loaded_item.price)
         changedCnt += 1
      s.price = loaded_item.price
      s.oldPrice = loaded_item.oldPrice
      result.append(s)

   for l in loaded:
      if l.id in [r.id for r in result]:
         continue
      newCnt += 1
      l.comment += '[new]'
      result.append(l)
   result.sort(key=lambda x: int(x.year) * 1000000 + int(x.gb) + int(x.ram) * (100 if int(x.ram) > 4 else 1), reverse=True)

   return result, removedCnt, changedCnt, newCnt, restoredCnt

if __name__ == '__main__':
   import sys
   init()

   loaded_items = []
   dumped_items = []

   clear()
   short = False
   while True:
      print('=' * 20)
      dumped = restore(short)
      output(dumped)
      c = menu()

      output(dumped)
      print('=' * 20)
      print()

      if c == 'q':
         break
      elif c == 's':
         short = not short         
      elif c in ['r']:
         short = False
         dumped = restore(short)

         print('Min price: {}, Max price: {}, Query: {}'.format(minPrice, maxPrice, query))
         processed = processAvito(minPrice, maxPrice)
         y = processYoula(minPrice, maxPrice)
         processed.extend(y)

         processed.sort(key=lambda x: int(x.year) * 1000000 + int(x.gb) + int(x.ram) * (100 if int(x.ram) > 4 else 1), reverse=True)

         print('Processing result:')
         result, removedCnt, changedCnt, newCnt, restoredCnt = merge(dumped, processed)
         if removedCnt + changedCnt + newCnt > 0:
            output(result)
            print('-' * 20)
            print('Summary:')
            print('* Removed:', removedCnt)
            print('* Restored:', restoredCnt)
            print('* Changed:', changedCnt)
            print('* New:', newCnt)

            save(result)
      elif c in ['p']:
         v = [ 'minPrice',
               'maxPrice',
               'redPrice',
               'greenPrice'
              ];
         i = 0
         for n in v:
            print('{}: {} ({})'.format(i, n, globals()[n]))
            i += 1
         print('q. Quite')
         print()
         print('Choice: ', end='')
         c = input().lower()
         if c in ['q']:
            clear()
            continue
         
         i = int(c)
         varName = v[i]
         print('New "{}": '.format(varName), end = '')

         globals()[varName] = int(input())
      elif c in ['d']:
         print('Downloading data file...')
         urlretrieve('https://github.com/cherezov/macbook_finder/blob/master/avito_apple.data?raw=true', dataFileNameDef)
         print('Done')
      else:
         try:
            c = int(c.strip())
            if c > len(dumped):
               continue 
         except Exception as e: 
            continue

         itemToChange = dumped[c]

         fullDump = restore(False)
         i = 0
         for f in fullDump:
            if f.id == itemToChange.id:
               break
            i += 1

         while edit_dialog(fullDump, i):
            save(fullDump)
      clear()

   clear()
