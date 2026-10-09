import sys,re,datetime as dt
from collections import Counter
ORD=["First","Second","Third","Fourth","Fifth","Sixth","Seventh","Eighth","Ninth","Tenth","Eleventh","Twelfth","Thirteenth","Fourteenth","Fifteenth","Sixteenth","Seventeenth","Eighteenth","Nineteenth","Twentieth","Twenty-First","Twenty-Second","Twenty-Third","Twenty-Fourth","Twenty-Fifth","Twenty-Sixth","Twenty-Seventh","Twenty-Eighth"]
def easter(y):
    a=y%19;b=y//100;c=y%100;d=b//4;e=b%4;f=(b+8)//25;g=(b-f+1)//3;h=(19*a+b-d-g+15)%30;i=c//4;k=c%4;l=(32+2*e+2*i-h-k)%7;m=(a+11*h+22*l)//451
    mo=(h+l-7*m+114)//31;da=(h+l-7*m+114)%31+1;return dt.date(y,mo,da)
def advent1(y):
    x=dt.date(y,12,25); x-=dt.timedelta(days=(x.weekday()+1)%7 or 7); return x-dt.timedelta(weeks=3)
def name(d):
    W=dt.timedelta
    y=d.year; E=easter(y); A=advent1(y)
    ly=A.year if d>=A else y-1; letter="ABC"[advent1(ly).year%3]
    if d.month==12 and d.day==24: return "Christmas Eve",letter
    if d.month==12 and d.day==25: return "Christmas Day",letter
    if d>=A:
        if d.weekday()==6 and d<dt.date(y,12,24): return f"{ORD[(d-A).days//7]} Sunday of Advent",letter
        if d.weekday()==6: return "First Sunday after Christmas",letter
        return None,letter
    if d.weekday()!=6:
        for off,n in [(-46,"Ash Wednesday"),(-3,"Maundy Thursday"),(-2,"Good Friday"),(-1,"Holy Saturday"),(39,"Ascension of the Lord")]:
            if d==E+W(days=off): return n,letter
        return None,letter
    # Sundays
    if d.month==1 and 2<=d.day<=6: return "Epiphany of the Lord",letter
    if d.month==1 and d.day==1: return "First Sunday after Christmas",letter
    ash=E-W(days=46); trans=ash-W(days=3)
    jan6=dt.date(y,1,6); bapt=jan6+W(days=(6-jan6.weekday())%7 or 7)
    if d==bapt: return "Baptism of the Lord",letter
    if bapt<d<trans: return f"{ORD[(d-bapt).days//7]} Sunday after Epiphany",letter
    if d==trans: return "Transfiguration Sunday",letter
    if trans<d<E-W(days=7): return f"{ORD[(d-ash).days//7]} Sunday in Lent",letter
    if d==E-W(days=7): return "Palm/Passion Sunday",letter
    if d==E: return "Easter Sunday",letter
    P=E+W(days=49)
    if E<d<P: return f"{ORD[(d-E).days//7]} Sunday of Easter",letter
    if d==P: return "Day of Pentecost",letter
    if d==P+W(days=7): return "Trinity Sunday",letter
    return f"{ORD[(d-P).days//7-1]} Sunday after Pentecost",letter
t=open(sys.argv[1],encoding='utf-8').read().replace('\r\n ','').replace('\n ','')
tot=ok=0;bad=Counter();ex=[]
for e in re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT',t,re.S):
    ds=re.search(r'DTSTART[^:]*:(\d+)',e).group(1); s=re.search(r'SUMMARY:(.*)',e).group(1).strip().replace('\\,',',')
    d=dt.date(int(ds[:4]),int(ds[4:6]),int(ds[6:8]))
    m=re.match(r'(.*?),\s*[Yy]ear ([ABC])$',s); sn,sl=(m.group(1),m.group(2)) if m else (s,None)
    cn,cl=name(d); tot+=1
    if cn and cn.lower()==sn.lower() and cl==sl: ok+=1
    else:
        kind='year' if cn and cn.lower()==sn.lower() else 'name'
        bad[kind]+=1; ex.append((str(d),sn,sl,cn,cl))
print('total',tot,'exact(case-insens)',ok,dict(bad))
for x in ex: print(x)
