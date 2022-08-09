
from .forms import UploadDataFileForm,ForecastForm
from django.http import HttpResponse
import os
from django.contrib.auth.decorators import login_required
from django.contrib.auth import  logout
from django.shortcuts import redirect, render

from django.views.decorators.cache import cache_control

from django.templatetags.static import static

import pandas as pd
import numpy as np
import os
# from matplotlib import pyplot as plt
from lightgbm import LGBMRegressor

from datetime import date
import datetime
from datetime import datetime, timedelta
import calendar



# Create your views here.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def UploadDataFileView(request):
    user_name = request.user.username
    upload_form = UploadDataFileForm()
    forecast_form= ForecastForm()
    context = {
        'upload_form': upload_form,
        'forecast_form': forecast_form,
        'bool_alert': 0,
        'user_name': user_name
    }
    isExist = os.path.exists("static/documents/DashData.xlsx")
    if isExist == True:
        context["bool_alert"] = 1


    if request.method == 'POST':
        if 'hidden_upload_field' in request.POST:
            print("POST Upload ---------")
            upload_form = UploadDataFileForm(request.POST,request.FILES)
            if upload_form.is_valid():
                upload_form.save()
                context["bool_alert"]  = 1
                return render(request, 'uploadFiles/upload.html', context)
        if 'hidden_forecat_field' in request.POST:
            isExist = os.path.exists("static/documents/DashData.xlsx")
            if isExist == False:
                context["bool_alert"]  = 0
                return render(request, 'uploadFiles/upload.html', context)
            else :
                forecastDataView(request)  #Call the function
                ########## Export the data and download it to the local machine of the the client
                path = 'static/documents/forecastIAFile.xlsx'
                with open(path, 'rb') as f:
                    data = f.read()
                response = HttpResponse(data, content_type='text/xlsx')
                response['Content-Disposition'] = 'attachment; filename = "forecastIAFile.xlsx"'
                #####################################################################
                return response #######Reponse the file to download


    return render(request, 'uploadFiles/upload.html', context)




# Create your views here.
def forecastDataView(request):
    ##Inner functions for the treatements  ########################################


    def crossJoinDataFrames(df1, df2):
        """In pandas we don't have cross join. So to perform cross join,
         we will create  a key column in both the DataFrames to
         merge on that key. """
        df1['key'] = 1
        df2['key'] = 1
        result = pd.merge(df1, df2, on='key').drop("key", 1)
        return result

    def associatePeriodeMonth(historiqueCAMarge):
        k = historiqueCAMarge.periode.unique()
        df = pd.DataFrame(k)
        df.rename(columns={0: 'periode'}, inplace=True)
        df['periode'] = df['periode'].apply(lambda x: datetime.strptime(x, '%Y-%m'))
        df = df.sort_values(by='periode')
        col = []
        for i in range(0, df.shape[0]):
            # col.append("Month" + str(i ))
            col.append(i)
        df["months"] = col
        return df

    def createDf(df, realCaORMarge):
        k = df.CodeDepartement.unique()
        dftopredict = pd.DataFrame(k)
        dftopredict.rename(columns={0: 'CodeDepartement'}, inplace=True)
        dftopredict["Month"] = 0
        dftopredict[realCaORMarge] = 0
        dftopredict['Last_month_lag'] = 0
        dftopredict['Last_month_Diff'] = 0
        return dftopredict

    def reformateData(depatmentsCombination, historiqueCAMarge, df_period_nbrMonth, realCaORMarge):
        """
        depatmentsCombination : (924, 4) : columns = {'bu', 'ctt', 'ope', 'pthrough ?'}
        historiqueCAMarge : (119121, 7),  columns = {'periode', 'bu', 'ctt', 'ope', 'pthrough ?', 'ca mois', 'mg mois'}
        df_period_nbrMonth : (62, 2): columns = {'periode', 'months'}
        """

        nbrCols = historiqueCAMarge["periode"].unique().shape[0]  # number of months in columns
        nbrRows = depatmentsCombination.shape[0]  ##Number of departments in rows

        ##Create a dataFrame with 'nbrCols +1' One column for the departementCode and 'number of months' other columns
        cols = []
        for i in range(0, nbrCols):
            cols.append(i)

        df_final = pd.DataFrame(index=range(0, nbrRows), columns=cols, data=0)
        df_final.reset_index(inplace=True)
        df_final = df_final.rename(columns={'index': 'CodeDepartement'})
        ### create the content of the columns, each case contains the CA or marge of the code departement in the specific date of periode

        for i in range(0, nbrRows):
            sub_df2 = historiqueCAMarge.loc[(historiqueCAMarge["bu"] == depatmentsCombination._get_value(i, "bu")) &
                                            (historiqueCAMarge["ctt"] == depatmentsCombination._get_value(i, "ctt")) &
                                            (historiqueCAMarge["ope"] == depatmentsCombination._get_value(i, "ope")) &
                                            (historiqueCAMarge["pthrough ?"] == depatmentsCombination._get_value(i, "pthrough ?"))]

            CA_sub_df2 = sub_df2.groupby(['periode'])[realCaORMarge].sum()
            df4 = pd.DataFrame(CA_sub_df2)
            df4["periode"] = df4.index
            df4.reset_index(drop=True, inplace=True)
            df4['periode'] = df4['periode'].apply(lambda x: datetime.strptime(x, '%Y-%m'))
            dfmerge = df_period_nbrMonth.merge(df4, on='periode', how='left')
            dfmerge = dfmerge.fillna(0)

            rowToInsert = dfmerge[
                realCaORMarge].tolist()  # create a list in order to insert it directely as a row in the dataframe
            rowToInsert.insert(0,i)  ##here we add the code of the departement in order to get a row in the same lenght as those of our dataframe
            df_final.loc[i] = rowToInsert
        return df_final

    def create_6_FeatureEngin(melt6, realCaORMarge):
        melt6['Last_month_lag'] = melt6.groupby(['CodeDepartement'])[realCaORMarge].shift(fill_value=0)
        melt6['Last_month_Diff'] = melt6.groupby(['CodeDepartement'])['Last_month_lag'].diff()

        melt6['Last-1_month_lag'] = melt6.groupby(['CodeDepartement'])[realCaORMarge].shift(2, fill_value=0)
        melt6['Last-1_month_Diff'] = melt6.groupby(['CodeDepartement'])['Last-1_month_lag'].diff()

        melt6['Last-2_month_lag'] = melt6.groupby(['CodeDepartement'])[realCaORMarge].shift(3, fill_value=0)
        melt6['Last-2_month_Diff'] = melt6.groupby(['CodeDepartement'])['Last-2_month_lag'].diff()

        melt6['Last-3_month_lag'] = melt6.groupby(['CodeDepartement'])[realCaORMarge].shift(4, fill_value=0)
        melt6['Last-3_month_Diff'] = melt6.groupby(['CodeDepartement'])['Last-3_month_lag'].diff()

        melt6['Last-4_month_lag'] = melt6.groupby(['CodeDepartement'])[realCaORMarge].shift(5, fill_value=0)
        melt6['Last-4_month_Diff'] = melt6.groupby(['CodeDepartement'])['Last-4_month_lag'].diff()

        melt6['Last-5_month_lag'] = melt6.groupby(['CodeDepartement'])[realCaORMarge].shift(6, fill_value=0)
        melt6['Last-5_month_Diff'] = melt6.groupby(['CodeDepartement'])['Last-5_month_lag'].diff()

        melt6['Last-6_month_lag'] = melt6.groupby(['CodeDepartement'])[realCaORMarge].shift(7, fill_value=0)
        melt6['Last-6_month_Diff'] = melt6.groupby(['CodeDepartement'])['Last-6_month_lag'].diff()

        melt6['Last-7_month_lag'] = melt6.groupby(['CodeDepartement'])[realCaORMarge].shift(8, fill_value=0)
        melt6['Last-7_month_Diff'] = melt6.groupby(['CodeDepartement'])['Last-7_month_lag'].diff()

        melt6['Last-8_month_lag'] = melt6.groupby(['CodeDepartement'])[realCaORMarge].shift(9, fill_value=0)
        melt6['Last-8_month_Diff'] = melt6.groupby(['CodeDepartement'])['Last-8_month_lag'].diff()

        melt6['Last-9_month_lag'] = melt6.groupby(['CodeDepartement'])[realCaORMarge].shift(10, fill_value=0)
        melt6['Last-9_month_Diff'] = melt6.groupby(['CodeDepartement'])['Last-9_month_lag'].diff()

        melt6['Last-10_month_lag'] = melt6.groupby(['CodeDepartement'])[realCaORMarge].shift(11, fill_value=0)
        melt6['Last-10_month_Diff'] = melt6.groupby(['CodeDepartement'])['Last-10_month_lag'].diff()

        melt6 = melt6.fillna(0)

        return melt6

    def forecastCA_XGBoosting2(dfToPtredict, maxMonth, maxMonth_to_predict, melt2, realCaORMarge, forecastCaOrMarge):

        '''
        #######################################################
        #This methode to fit the model and predict the future #
        #######################################################


        #dfToPtredict : a dataframe that contains the inputs which permet us to predict the next months (on dataframe per month)

        #maxMonth : the number associated to the last month od the dataframe which containes the full informations (ca et marge), it can be the current month or the last month

        #melt2 : the dataframe we use to fit the model, it contains the full infoormation (ca et marge)

        # realCaORMarge, forecastCaOrMarge : string : realCaORMarge = {'ca mois', }, forecastCaOrMarge={'Forecast CA Month', 'Forecast Marge Month'}

        '''

        # melt2 = create_6_FeatureEngin(melt2,realCaORMarge)

        for month in range(maxMonth, maxMonth_to_predict+1):
            dfToPtredict["Month"] = month
            melt2 = pd.concat([melt2, dfToPtredict], axis=0)
            melt2.reset_index(drop=True,
                              inplace=True)  # drop =true ie delete the column index that will be created after the reset, inplace =true ie
            # replace melt2 by the new one ie don"t create a copy of melt2 modified

            # --------------------------------------------------------------------------------Fenetreglissante---------------
            melt2.loc[melt2['Month'] == month, 'Last_month_lag'] = melt2.groupby(['CodeDepartement'])[
                realCaORMarge].shift(fill_value=0)
            melt2['Last_month_Diff'] = melt2.groupby(['CodeDepartement'])['Last_month_lag'].diff()

            melt2.loc[melt2['Month'] == month, 'Last_month-1_lag'] = melt2.groupby(['CodeDepartement'])[
                realCaORMarge].shift(2, fill_value=0)
            melt2['Last-1_month_Diff'] = melt2.groupby(['CodeDepartement'])['Last_month-1_lag'].diff()

            melt2.loc[melt2['Month'] == month, 'Last_month-2_lag'] = melt2.groupby(['CodeDepartement'])[
                realCaORMarge].shift(3, fill_value=0)
            melt2['Last_month-2_Diff'] = melt2.groupby(['CodeDepartement'])['Last_month-2_lag'].diff()

            melt2.loc[melt2['Month'] == month, 'Last_month-3_lag'] = melt2.groupby(['CodeDepartement'])[
                realCaORMarge].shift(4, fill_value=0)
            melt2['Last_month-3_Diff'] = melt2.groupby(['CodeDepartement'])['Last_month-3_lag'].diff()

            melt2.loc[melt2['Month'] == month, 'Last_month-4_lag'] = melt2.groupby(['CodeDepartement'])[
                realCaORMarge].shift(5, fill_value=0)
            melt2['Last_month-4_Diff'] = melt2.groupby(['CodeDepartement'])['Last_month-4_lag'].diff()

            melt2['Last-5_month_lag'] = melt2.groupby(['CodeDepartement'])[realCaORMarge].shift(6, fill_value=0)
            melt2['Last-5_month_Diff'] = melt2.groupby(['CodeDepartement'])['Last-5_month_lag'].diff()

            melt2['Last-6_month_lag'] = melt2.groupby(['CodeDepartement'])[realCaORMarge].shift(7, fill_value=0)
            melt2['Last-6_month_Diff'] = melt2.groupby(['CodeDepartement'])['Last-6_month_lag'].diff()

            melt2['Last-7_month_lag'] = melt2.groupby(['CodeDepartement'])[realCaORMarge].shift(8, fill_value=0)
            melt2['Last-7_month_Diff'] = melt2.groupby(['CodeDepartement'])['Last-7_month_lag'].diff()

            melt2['Last-8_month_lag'] = melt2.groupby(['CodeDepartement'])[realCaORMarge].shift(9, fill_value=0)
            melt2['Last-8_month_Diff'] = melt2.groupby(['CodeDepartement'])['Last-8_month_lag'].diff()

            melt2['Last-9_month_lag'] = melt2.groupby(['CodeDepartement'])[realCaORMarge].shift(10, fill_value=0)
            melt2['Last-9_month_Diff'] = melt2.groupby(['CodeDepartement'])['Last-9_month_lag'].diff()

            melt2['Last-10_month_lag'] = melt2.groupby(['CodeDepartement'])[realCaORMarge].shift(11, fill_value=0)
            melt2['Last-10_month_Diff'] = melt2.groupby(['CodeDepartement'])['Last-10_month_lag'].diff()

            melt2.fillna(0)
            # --------------------------------------------------------------------------------Fenetreglissante---------------

            train = melt2[melt2['Month'] < month]
            val = melt2[melt2['Month'] == month]

            xtr, xts = train.drop([realCaORMarge], axis=1), val.drop([realCaORMarge], axis=1)
            ytr, yts = train[realCaORMarge].values, val[realCaORMarge].values
            # mdl = LGBMRegressor(n_estimators=1000, learning_rate=0.01)
            mdl = LGBMRegressor(subsample=0.75, reg_lambda=1.4, reg_alpha=1.2, num_leaves=16,
                                n_estimators=500, max_depth=3, max_bin=510, learning_rate=0.03, colsample_bytree=0.64,
                                boosting_type='dart')

            # mdl =  XGBRegressor(colsample_bytree= 0.7, learning_rate= 0.03, max_depth= 5, min_child_weight= 4, n_estimators= 1000, nthread= 4,objective= 'reg:linear',  subsample= 0.7)

            mdl.fit(xtr, ytr)

            p = mdl.predict(xts, iteration_range=(0, 6))

            melt2.loc[melt2['Month'] == month, realCaORMarge] = p  # -------------------------------Fenetreglissante

        melt2.loc[melt2["Month"] >= maxMonth, forecastCaOrMarge] = melt2.loc[
            melt2["Month"] >= (maxMonth), realCaORMarge]

        melt2.loc[melt2["Month"] >= maxMonth, realCaORMarge] = np.NaN

        return melt2

    def lastformatData(maxMonth_to_predict, meltx, depatmentsCombination, realCaORMarge, forecastCaOrMarge):
        '''
        realCaORMarge, forecastCaOrMarge : string : realCaORMarge = {'ca mois', }, forecastCaOrMarge={'Forecast CA Month', 'Forecast Marge Month'}
        '''
        meltx["Month"].unique().size
        dd = pd.DataFrame()
        dd['periode'] = pd.date_range(start='2017-04-01', periods=int(maxMonth_to_predict ), freq='M').tolist()
        dd["Month"] = dd.index
        meltx = meltx.merge(dd, how='left', on='Month')

        depatmentsCombination["CodeDepartement"] = depatmentsCombination.index
        meltx = meltx.merge(depatmentsCombination, how="left", on="CodeDepartement")
        meltx = meltx[["Month", "periode", 'bu', 'ctt', 'ope', 'pthrough ?', realCaORMarge, forecastCaOrMarge]]
        return meltx
    ###############################################################################
    ##############################################################################

    ###Data Load ##################################################################

    file_url = static('/documents/forecastdata_7.xlsx')
    # in production use file_url because it has slash
    response = HttpResponse()
    Departements = pd.read_excel('static/documents/Departments.xlsx', sheet_name='Departements')
    ctt = pd.read_excel('static/documents/Departments.xlsx', sheet_name='ctt')
    typeOpe = pd.read_excel('static/documents/Departments.xlsx', sheet_name='typeOpe')
    sousTraitance = pd.read_excel('static/documents/Departments.xlsx', sheet_name='SousTraitance')
    df_final = pd.read_excel('static/documents/forecastIAFile.xlsx', sheet_name='ForecastIA')
    historiqueCAMarge = pd.read_excel("static/documents/DashData.xlsx")

    os.remove('static/documents/DashData.xlsx')
    ###############################################################################
    ##############################################################################

    historiqueCAMarge = historiqueCAMarge[["période", 'bu', "ctt", "opé", 'pthrough ?', 'ca mois', 'mg mois']]
    historiqueCAMarge.rename(columns={"période": "periode", "opé": "ope"}, inplace=True)

    ####   MAIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIN   ###################

    # join the dataframes in order to create all the possible combinations
    result1 = crossJoinDataFrames(Departements, ctt)
    result2 = crossJoinDataFrames(result1, typeOpe)
    depatmentsCombination = crossJoinDataFrames(result2, sousTraitance)
    # depatmentsCombination

    ## transform the data to the format we need
    df_period_nbrMonth = associatePeriodeMonth(historiqueCAMarge)
    #################################################################################################

    ################################################################################################

    df2_ca = reformateData(depatmentsCombination, historiqueCAMarge, df_period_nbrMonth, "ca mois")
    df2_marge = reformateData(depatmentsCombination, historiqueCAMarge, df_period_nbrMonth, "mg mois")

    meltca = df2_ca.melt(id_vars='CodeDepartement', var_name='Month', value_name='ca mois')
    meltca = meltca.sort_values(['Month', 'CodeDepartement'])

    meltMarge = df2_marge.melt(id_vars='CodeDepartement', var_name='Month', value_name='mg mois')
    meltMarge = meltMarge.sort_values(['Month', 'CodeDepartement'])

    dfToPtredictCA = createDf(meltca, "ca mois")
    dfToPtredictMarge = createDf(meltca, "mg mois")

    maxMonth = meltca.Month.max()
    meltca = create_6_FeatureEngin(meltca, 'ca mois')
    #
    ####################################################################
    ###We need to drop current month related information
    currentDate = datetime.now()
    lastDayOfCurentMonth = datetime(currentDate.year, currentDate.month,
                                    calendar.monthrange(currentDate.year, currentDate.month)[1])
    firstDayOfCurentMonth = datetime(currentDate.year, currentDate.month, 1)
    numCurrentMonth = maxMonth + 1  # in case we don't have information about the current month
    serieCurrentMonth = df_period_nbrMonth.loc[df_period_nbrMonth[
                                                   "periode"] == firstDayOfCurentMonth].months.unique()  # [0] #to get the number of the curent month
    if serieCurrentMonth.size > 0:
        numCurrentMonth = serieCurrentMonth[0]

    #######################################################################################
    meltca.drop(meltca[meltca['Month'] >= numCurrentMonth].index, inplace=True)

    meltMarge = create_6_FeatureEngin(meltMarge, 'mg mois')
    meltMarge.drop(meltMarge[meltMarge['Month'] >= numCurrentMonth].index, inplace=True)

    ######################################################################################
    maxMonth = meltca.Month.max()  ##the new one after drop (there are two cases : drop and not drop ), here we are sure that we don't have the current month
    maxMonth_to_predict = maxMonth + 6
    meltCaForecastReal = forecastCA_XGBoosting2(dfToPtredictCA, maxMonth, maxMonth_to_predict, meltca, 'ca mois',
                                                'Forecast CA Month')

    meltMgForecastReal = forecastCA_XGBoosting2(dfToPtredictMarge, maxMonth, maxMonth_to_predict, meltMarge, 'mg mois',
                                                'Forecast Mg Month')


    meltCaForecastReal = lastformatData(maxMonth_to_predict, meltCaForecastReal, depatmentsCombination, "ca mois",
                                        "Forecast CA Month")

    meltMgForecastReal = lastformatData(maxMonth_to_predict, meltMgForecastReal, depatmentsCombination, "mg mois",
                                        "Forecast Mg Month")

    meltForecastReal = meltCaForecastReal.merge(meltMgForecastReal, how="left",
                                                on=["periode","Month", "bu", "ctt", "ope", "pthrough ?"])


    df_final.loc[(df_final["Month"] >= numCurrentMonth)] = meltForecastReal.loc[
        meltForecastReal["Month"] >= numCurrentMonth]

    ###############insert the rested values
    new_rows = meltForecastReal.loc[meltForecastReal["Month"] == maxMonth_to_predict]
    df_final = df_final.append(new_rows, ignore_index=True)
    df_final.to_excel('static/documents/forecastIAFile.xlsx',
                              sheet_name='ForecastIA', index=False)




