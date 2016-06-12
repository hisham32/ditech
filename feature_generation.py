import pandas as pd
from datetime import date, timedelta
import numpy as np

startdate = date(2016, 1 ,1)
total_datelist = [startdate+timedelta(days=i) for i in xrange(3,21)]
train_datelist = [startdate+timedelta(days=i-1) for i in [5,6,7,8,10,11,12,13,14,15,16,18,20]]
validation_datelist = [startdate+timedelta(days=i-1) for i in [4,9,17,19,21]]
test_datelist = [startdate+timedelta(days=i) for i in xrange(22,31,2)]
region_table = pd.read_table("season_1/training_data/cluster_map/cluster_map", index_col=0, names=['hash', 'id'])

def gap_level(a):
    if a==0: return 0;
    elif a<=1: return 1;
    elif a<=3: return 2;
    elif a<=6: return 3;
    elif a<=12: return 4;
    elif a<=30: return 5;
    else: return 6;
    
def customer_level(a):
    if a<=10: return 0;
    elif a<=20: return 1;
    else: return 2;
    
def dgap_level(a):
    if a<0: return 0;
    elif a==0: return 1;
    else: return 2;
    
def ddemand_level(a):
    if a<0: return 0;
    elif a==0: return 1;
    else: return 2;

def weather_feature_generation(path, datelist):
    """generated weather feature is a numpy 2d array of length 144 x len(datelist).
    Each feature is 9 elements long
    """
    # aggregration first
    weatherlist = []
    for d in datelist:
        weather = pd.read_table(path+"/weather_data/weather_data_"+d.isoformat(), 
                                names=['time','weather','temperature','pm'], parse_dates=[0])
        time_slot = np.zeros((weather.shape[0],),np.int)
        jour = np.zeros((weather.shape[0],), date)
        for i, t in enumerate(weather['time']):
            time_slot[i] = t.time().hour*6+t.time().minute/10
            jour[i] = t.date()
        weather['slot'] = time_slot
        weather['jour'] = jour
        weatherlist.append(weather)
    grouped_weatherlist = pd.concat(weatherlist).groupby(['jour', 'slot'])
    # generation second
    weather_feature = np.zeros((len(datelist)*144, 9), dtype = np.float)
    for i, dt in enumerate(datelist):
        for j in xrange(144):
            try:
                rec = grouped_weatherlist.get_group((dt, j))
                for k in xrange(rec.shape[0]):
                    weather_feature[i*144+j, rec.iloc[k,1]-1] += 1.0/rec.shape[0]
            except KeyError:
                continue;
    # post processing of weather feature, using linear interplotation
    b = -1
    for e in xrange(weather_feature.shape[0]+1):
        if e==weather_feature.shape[0] or not np.all(weather_feature[e,:]==0.0):
            if e==weather_feature.shape[0]:
                if b!=e-1:
                    for i in xrange(b+1, e):
                        weather_feature[i, :] = weather_feature[b, :]
                break;

            if not np.all(weather_feature[e,:]==0.0) and b!=e-1:
                r = e-b+0.0
                for i in xrange(b+1, e):
                    weather_feature[i, :] = (e-i)/r*weather_feature[b, :] + (i-b)/r*weather_feature[e, :]
            elif b==-1 and b!=e-1:
                for i in xrange(b+1, e):
                    weather_feature[i, :] = weather_feature[e, :]
            b=e
    return weather_feature
    
def traffic_generation(path, datelist):
    vtraffic = []
    for d in datelist:
        traffic_table = pd.read_table(path+"/traffic_data/traffic_data_"+d.isoformat(), names=['district', 
                'one', 'two', 'three', 'four', 'time'], parse_dates=[5])
        traffic = traffic_table[['one', 'two', 'three', 'four']].applymap(lambda x: int(x.split(':')[1]))
        traffic = traffic.div(traffic.sum(axis=1), axis=0)
        traffic['slot'] = traffic_table.time.apply(lambda x: x.hour*6+x.minute/10)
        traffic['date'] = traffic_table.time.apply(lambda x: x.day)
        traffic['district'] = traffic_table.district.apply(lambda x: region_table.ix[x, 0])
        vtraffic.append(traffic)
    grouped_traffic = pd.concat(vtraffic).groupby(['date','district','slot'])
    return grouped_traffic
    
def training_first_order(order_table):
    grouped_order = order_table.groupby('depart_id')
    delta = []
    for destrict in xrange(1, 67):
        destrict_order = grouped_order.get_group(destrict).copy()
        gap = destrict_order['order_id']-destrict_order['driver_id']
        dgap = np.zeros(gap.shape)
        for i in xrange(1, dgap.shape[0]):
            dgap[i] = gap.iloc[i]-gap.iloc[i-1]
        ddemand = np.zeros(destrict_order['order_id'].shape)
        for i in xrange(1, ddemand.shape[0]):
            ddemand[i] = destrict_order['order_id'].iloc[i] - destrict_order['order_id'].iloc[i-1]
        destrict_order['dgap']=dgap
        destrict_order['ddemand']=ddemand
        delta.append(destrict_order)
    dor = pd.concat(delta)
    return dor
    
def test_first_order(order_table, datelist):
    grouped_order = order_table.groupby(['jour', 'depart_id'])
    delta = []
    for dt in datelist:
        for destrict in xrange(1, 67):
            destrict_order = grouped_order.get_group((dt, destrict)).copy()
            gap = destrict_order['order_id']-destrict_order['driver_id']
            dgap = np.zeros(gap.shape)
            for i in xrange(1, dgap.shape[0]):
                dgap[i] = gap.iloc[i]-gap.iloc[i-1]
            ddemand = np.zeros(destrict_order['order_id'].shape)
            for i in xrange(1, ddemand.shape[0]):
                ddemand[i] = destrict_order['order_id'].iloc[i] - destrict_order['order_id'].iloc[i-1]
            destrict_order['dgap']=dgap
            destrict_order['ddemand']=ddemand
            delta.append(destrict_order)
    dor = pd.concat(delta)
    return dor

# read order records
def refine_order_list(path, datelist):
    order_table_list = []
    for d in datelist:
        order_table = pd.read_table(path+"/order_data/order_data_"+d.isoformat(), 
                                    names=['order_id', 'driver_id', 'passenger_id', 'depart_id', 'dest_id', 'price', 'time'], 
                                    parse_dates=[6])
        time_slot = np.zeros((order_table.shape[0],),np.int)
        jour = np.zeros((order_table.shape[0],), date)
        for i, t in enumerate(order_table['time']):
            time_slot[i] = t.time().hour*6+t.time().minute/10
            jour[i] = t.date()
        order_table['time_slot']=time_slot
        order_table['jour']=jour
        order_table['depart_id'] = order_table['depart_id'].apply(lambda x: region_table.ix[x, 'id'])
        order_table_list.append(order_table)
    order_table = pd.concat(order_table_list).loc[:,['jour', 'depart_id', 'time_slot', 'order_id', 'driver_id']]# all necessary information, at least what I considered to be necessary.
    f = order_table.groupby(by=['jour', 'depart_id', 'time_slot'], as_index=False).count()
    return f
    
def training_data_generation(order_table, whole_grouped_order_table, weather_feature, grouped_traffic):
    # flst is the final feature
    flst = []
    # generate time feature
    for i in xrange(order_table.shape[0]):
        x = [(order_table.ix[i, 'time_slot']/6, 1), (24+order_table.ix[i, 'jour'].weekday()/5, 1)]
        flst.append(x)
    # generate region feature
    for i in xrange(order_table.shape[0]):
        flst[i].append((26+order_table.ix[i, 'depart_id']-1, 1))
    # generate customer feature
    dd = timedelta(days=7)
    for i in xrange(order_table.shape[0]):
        bd = order_table.ix[i, 'jour']-dd
        try:
            rec = whole_grouped_order_table.get_group((bd, order_table.ix[i, 'depart_id'], order_table.ix[i, 'time_slot']))
            gp = rec.iloc[0, 3]-rec.iloc[0, 4]
            demand = rec.iloc[0, 3]
            flst[i].append((92+3*gap_level(gp)+customer_level(demand), 1))
        except KeyError:
            pass;
            
        if order_table.ix[i, 'time_slot']==0:
            pd = order_table.ix[i, 'jour'] - timedelta(days=1)
            pt = 143
        else:
            pd = order_table.ix[i, 'jour']
            pt = order_table.ix[i, 'time_slot']-1
        try:
            rec = whole_grouped_order_table.get_group((pd, order_table.ix[i, 'depart_id'], pt))
            gp = rec.iloc[0, 3]-rec.iloc[0, 4]
            demand = rec.iloc[0, 3]
            flst[i].append((113+3*gap_level(gp)+customer_level(demand), 1))
        except KeyError:
            pass;
            
        if order_table.ix[i, 'time_slot']==1:
            p2d = order_table.ix[i, 'jour'] - timedelta(days=1)
            p2t = 143
        else:
            p2d = order_table.ix[i, 'jour']
            p2t = order_table.ix[i, 'time_slot']-2
        try:
            rec2 = whole_grouped_order_table.get_group((p2d, order_table.ix[i, 'depart_id'], p2t))
            gp2 = rec2.iloc[0, 3]-rec2.iloc[0, 4]
            demand = rec2.iloc[0, 3]
            flst[i].append((134+3*gap_level(gp2)+customer_level(demand), 1))
            flst[i].append((155+7*gap_level(gp)+gap_level(gp2), 1))
        except KeyError:
            pass;
        
    # weather feature
    #for i in xrange(order_table.shape[0]):
    #    wf = weather_feature[order_table.ix[i, 'time_slot']+144*(order_table.ix[i, 'jour'].day-1), :]
    #    for idx in np.nonzero(wf)[0]:
    #        flst[i].append((326+idx, wf[idx]))
    # traffic feature
    #for i in xrange(order_table.shape[0]):
    #    try:
    #        rec = grouped_traffic.get_group((order_table.ix[i, 'jour'].day, 
    #        order_table.ix[i, 'depart_id'], 
    #        order_table.ix[i, 'time_slot']))
    #        flst[i].append((335, rec.iloc[0, 0]/5))
    #        flst[i].append((336, rec.iloc[0, 1]))
    #        flst[i].append((337, rec.iloc[0, 2]*5))
    #        flst[i].append((338, rec.iloc[0, 3]*5))
    #    except KeyError:
    #        pass;
    return flst
    
def test_data_generation(filename, whole_grouped_order_table, test_grouped_order_table, weather_feature, test_grouped_traffic):
    flst = []
    dd = timedelta(days=7)
    with open(filename, 'r') as fr:
        while True:
            r = fr.readline().strip()
            if not r: break;
            
            r = [int(itm) for itm in r.split('-')]
            #x = [(r[3]-1, 1), (144+(r[3]-1)/6, 1), (168+date(r[0], r[1], r[2]).weekday()/5, 1)]
            x = [((r[3]-1)/6, 1), (24+date(r[0], r[1], r[2]).weekday()/5, 1)]
            
            if r[3]==1:
                pd = date(r[0], r[1], r[2]) - timedelta(days=1)
                pt = 143
            else:
                pd = date(r[0], r[1], r[2])
                pt = r[3]-2
            
            if r[3]==2:
                p2d = date(r[0], r[1], r[2]) - timedelta(days=1)
                p2t = 143
            else:
                p2d = date(r[0], r[1], r[2])
                p2t = r[3]-3
                
            
            for t in xrange(66):
                xc = x[:]
                xc.append((26+t, 1))
                
                bd = date(r[0], r[1], r[2])-dd
                try:
                    rec = whole_grouped_order_table.get_group((bd, t+1, r[3]-1))
                    gp = rec.iloc[0, 3]-rec.iloc[0, 4]
                    demand = rec.iloc[0, 3]
                    xc.append((92+3*gap_level(gp)+customer_level(demand), 1))
                except KeyError:
                    pass;
                    
                try:
                    rec = test_grouped_order_table.get_group((pd, t+1, pt))
                    gp = rec.iloc[0, 3]-rec.iloc[0, 4]
                    demand = rec.iloc[0, 3]
                    xc.append((113+3*gap_level(gp)+customer_level(demand), 1))
                except KeyError:
                    pass;

                try:
                    rec2 = test_grouped_order_table.get_group((p2d, t+1, p2t))
                    gp2 = rec2.iloc[0, 3]-rec2.iloc[0, 4]
                    demand = rec2.iloc[0, 3]
                    xc.append((134+3*gap_level(gp2)+customer_level(demand), 1))
                    xc.append((155+7*gap_level(gp)+gap_level(gp2), 1))
                except KeyError:
                    pass;

                #wf = weather_feature[r[3]-1+144*((r[2]-22)/2), :]
                #for idx in np.nonzero(wf)[0]:
                #    xc.append((326+idx, wf[idx]))
                #    
                #try:
                #    rec = grouped_traffic.get_group((r[2], r[3], t+1))
                #    xc.append((335, rec.iloc[0, 0]/5))
                #    xc.append((336, rec.iloc[0, 1]))
                #    xc.append((337, rec.iloc[0, 2]*5))
                #    xc.append((338, rec.iloc[0, 3]*5))
                #except KeyError:
                #    pass;
                    
                flst.append(xc)
    return flst
    
def run():
    #weather_feature = weather_feature_generation("season_1/training_data", [startdate+timedelta(days=i) for i in xrange(0,21)])
    # get region table
    total_order = refine_order_list("season_1/training_data", total_datelist)
    total_grouped_order = total_order.groupby(['jour', 'depart_id', 'time_slot'])
    #grouped_traffic = traffic_generation("season_1/training_data", total_datelist)
    flst = training_data_generation(total_order, total_grouped_order, None, None)
    
    rst = total_order.jour.isin(train_datelist)
    train_feature = [flst[i] for i in rst[rst].index]  
    with open("training_data", 'w') as fw:
        for f, i in zip(train_feature, rst[rst].index):
            if total_order.ix[i, 'order_id']==total_order.ix[i, 'driver_id']: continue;
            s = '{0} {1} {2} {3} '.format(total_order.ix[i, 'order_id']-total_order.ix[i, 'driver_id'],
            total_order.ix[i, 'jour'].day, 
            total_order.ix[i, 'time_slot'], 
            total_order.ix[i, 'depart_id'])
            for idx, val in f:
                if val!=0: s+='{0}:{1} '.format(idx, val)
            s+='\n'
            fw.write(s)
            if total_order.ix[i, 'jour'].day==10 or total_order.ix[i, 'jour'].day==16:
                fw.write(s)
    
    rst = total_order.jour.isin(validation_datelist)
    valid_feature = [flst[i] for i in rst[rst].index]
    with open("validation1_data", 'w') as fw:
        for f, i in zip(valid_feature, rst[rst].index):
            if total_order.ix[i, 'order_id']==total_order.ix[i, 'driver_id']: continue;
            s = '{0} {1} {2} {3} '.format(total_order.ix[i, 'order_id']-total_order.ix[i, 'driver_id'],
            total_order.ix[i, 'jour'].day, 
            total_order.ix[i, 'time_slot'], 
            total_order.ix[i, 'depart_id'])
            for idx, val in f:
                if val!=0: s+='{0}:{1} '.format(idx, val)
            s+='\n'
            fw.write(s)
    
            
def run_test():
    #weather_feature = weather_feature_generation("season_1/training_data", [startdate+timedelta(days=i) for i in xrange(0,21)])
    # get region table
    train_order = refine_order_list("season_1/training_data", total_datelist)
    total_grouped_train_order = train_order.groupby(['jour', 'depart_id', 'time_slot'])
    
    #grouped_traffic = traffic_generation("season_1/training_data", total_datelist)
    flst = training_data_generation(train_order, total_grouped_train_order, None, None)
        
    with open("training_data_total", 'w') as fw:
        for i, features in enumerate(flst):
            if train_order.ix[i, 'order_id']==train_order.ix[i, 'driver_id']: continue;
            s = '{0} {1} {2} {3} '.format(train_order.ix[i, 'order_id']-train_order.ix[i, 'driver_id'],
            train_order.ix[i, 'jour'].day, 
            train_order.ix[i, 'time_slot'], 
            train_order.ix[i, 'depart_id'])
            for idx, val in features:
                if val!=0: s+='{0}:{1} '.format(idx, val)
            s+='\n'
            fw.write(s)
            if train_order.ix[i, 'jour'].day==10 or train_order.ix[i, 'jour'].day==16:
                fw.write(s)

    test_order = refine_order_list("season_1/test_set_2", test_datelist)
    grouped_test_order = test_order.groupby(['jour', 'depart_id', 'time_slot'])
    #weather_feature = weather_feature_generation("season_1/test_set_2/", test_datelist)
    #grouped_test_traffic = traffic_generation("season_1/test_set_2", test_datelist)
    flst = test_data_generation("season_1/test_set_2/read_me_2.txt", total_grouped_train_order, grouped_test_order, None, None)
    
    with open("test_data", 'w') as fw:
        for features in flst:
            s = ''
            for idx, val in features:
                if val!=0: s+='{0}:{1} '.format(idx, val)
            s+='\n'
            fw.write(s)
    
            
if __name__=='__main__':
    run_test()