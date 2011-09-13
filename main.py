#!/usr/bin/env python2.5
#
# Copyright 2011 Stephen Holiday.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import cgi
import datetime
from itertools import groupby

from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db

from pytz.gae import pytz

class MainPage(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()

        if user:
            self.response.out.write('<html><body><h1>Jobmine Stats</h1>Hello, ' + user.nickname())
            
            q = Pixel.all().filter('user = ', user).order('-date')
            results = q.fetch(1000)
            self.response.out.write("<h2>Pixels</h2><table border=\"1\"><tr><th>Name</th><th>Date</th><th>Pings</th></tr>")
            for p in results:
                self.response.out.write('<tr><td><a href="/ViewLog/%s/">%s</a></td><td>%s</td><td>%s</td></tr>' % (p.key(), p.name, format_datetime(p.date), p.views))
            self.response.out.write("</table>")
            self.response.out.write("""
            <h2>Add a New Pixel</h2>
            <form action="/Add/" method="post">
                 <div><input name="pixel_name" /></div>
                 <div><input type="submit" value="Add Tracking Pixel"></div>
            </form>
            
            """)
        else:
            self.redirect(users.create_login_url(self.request.uri))

class ViewLog(webapp.RequestHandler):
    def get(self, pixel_key):
        user = users.get_current_user()

        if user:
            pixel = db.get(pixel_key)
            
            q = PixelLog.all().ancestor(pixel).order('date')
            results = q.fetch(10000)
            table = ""
            points=''
            views=0
            for p in results:
                views+=1
                dt = dt_to_eastern(p.date)
                points = '%s\n[new Date(%s, %s, %s, %s, %s, %s, 0), %s],'%(points,dt.year,dt.month-1, dt.day, dt.hour, dt.minute, dt.second, views)
                ip = p.remote_addr
                country = getGeoIPCode(ip)
                flag = '<img src="http://geoip.wtanaka.com/flag/%s.gif"'%country
                table = "<tr><td>%s</td><td>%s</td><td>%s %s</td><td>%s</td></tr>\n%s"%(format_datetime(p.date), p.viewing_user, ip, flag, p.user_agent, table)
            self.response.out.write("""
                <html>
                <head>
                    <script type='text/javascript' src='https://www.google.com/jsapi'></script>
                    <script type='text/javascript'>
                      google.load('visualization', '1', {'packages':['annotatedtimeline']});
                      google.setOnLoadCallback(drawChart);
                      function drawChart() {
                        var data = new google.visualization.DataTable();
                        data.addColumn('datetime', 'Datetime');
                        data.addColumn('number', 'Views');
                        data.addRows([
                            %s
                        ]);

                        var chart = new google.visualization.AnnotatedTimeLine(document.getElementById('chart_div'));
                        chart.draw(data, {displayAnnotations: true});
                      }
                    </script>
                  </head>
                <body>"""%points.strip(','))
            
            self.response.out.write("<h2>Views (%s)</h2>"%pixel.views)
            self.response.out.write("<div id='chart_div' style='width: 700px; height: 240px;'></div>")
            self.response.out.write("<table border=\"1\"><tr><th>Date</th><th>User</th><th>IP</th><th>User Agent</th></tr>")
            
            self.response.out.write(table)
            self.response.out.write("</table>")
            
            img_tag=cgi.escape('<img src="http://jobminestats.appspot.com/Ping/%s.gif" height="0" width="0"/>'%pixel.key())
            
            self.response.out.write("""<h2>Tracking Code</h2>
                <textarea rows="2" cols="120">%s</textarea>
            """%img_tag)
            
            self.response.out.write("<p>Current Time %s</p>"%format_datetime(datetime.datetime.now()))
            
        else:
            self.redirect("/")
        


class Add(webapp.RequestHandler):
    def post(self):
        user = users.get_current_user()

        if user:
            pixel_name=cgi.escape(self.request.get('pixel_name'))
            p = Pixel(name=pixel_name, user=user, date=datetime.datetime.now(), views=0)
            p.put()
      
        self.redirect("/")
      
class Ping(webapp.RequestHandler):
    def get(self, pixel_key):
        def increment_views(key):
            obj = db.get(key)
            obj.views += 1
            obj.put()
            
        pixel = db.get(pixel_key)
        #self.response.out.write("PONG %s %s"%(pixel_key, pixel.name))
       
        remote_addr = self.request.remote_addr
        user_agent  = self.request.headers['User-Agent']
        
        viewing_user = users.get_current_user()
        pl = PixelLog(parent=pixel, date=datetime.datetime.now(), user=pixel.user, viewing_user=viewing_user, remote_addr=remote_addr, user_agent=user_agent)
        pl.put()
        
        db.run_in_transaction(increment_views, pixel_key)
        
        self.response.headers['Content-Type']='image/gif'
        self.response.headers['Last-Modified'] = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT")
        self.response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        self.response.headers['Expires'] = 'Sat, 26 Jul 1997 05:00:00 GMT'
        self.response.out.write(open('pixel.gif','r').read())
        
                 
class Pixel(db.Model):
    name = db.StringProperty(required=True)
    user = db.UserProperty(required=True)
    date = db.DateTimeProperty(required=True)
    views = db.IntegerProperty(required=True)
    
class PixelLog(db.Model):
    date = db.DateTimeProperty(required=True)
    user = db.UserProperty(required=True)
    viewing_user = db.UserProperty()
    remote_addr = db.StringProperty()
    user_agent = db.TextProperty()

eastern = pytz.timezone('US/Eastern')
utc=pytz.timezone('UTC')
def dt_to_eastern(dt):
    dt=dt.replace(tzinfo=utc)
    return dt.astimezone(eastern)
    
def format_datetime(dt):
    dt=dt.replace(tzinfo=utc)
    loc_dt = dt.astimezone(eastern)
    return loc_dt.strftime('%Y-%m-%d %H:%M:%S %Z')
      
application = webapp.WSGIApplication(
    [
        ('/', MainPage),
        (r'/ViewLog/(.*)/', ViewLog),
        (r'/Ping/(.*).gif', Ping),
        ('/Add/',Add),
    ],
    debug=True)
def main():
    run_wsgi_app(application)


def getGeoIPCode(ipaddr):
   '''
    From http://code.google.com/p/geo-ip-location/wiki/GoogleAppEngine
   '''
   from google.appengine.api import memcache
   memcache_key = "gip_%s" % ipaddr
   data = memcache.get(memcache_key)
   if data is not None:
      return data

   geoipcode = ''
   from google.appengine.api import urlfetch
   try:
      fetch_response = urlfetch.fetch(
            'http://geoip.wtanaka.com/cc/%s' % ipaddr)
      if fetch_response.status_code == 200:
         geoipcode = fetch_response.content
   except urlfetch.Error, e:
      pass

   if geoipcode:
      memcache.set(memcache_key, geoipcode)
   return geoipcode

if __name__ == "__main__":
    main()