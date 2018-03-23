import numpy as np
import ROOT as R
import os
import sys
import shutil
import copy
import json
import root_numpy as rn
import root_pandas as rp
from array import array

def main():
    from Reader import Reader
    from Plotter import Plotter
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-c', dest='channel', help='Decay channel' ,choices = ['mt','et','tt'], default = 'mt')
    parser.add_argument('-v', dest='var',   help='Variable to collect' , default = 'pred_prob')
    parser.add_argument('-a', dest='all',   help='Also write shape templates' , action = 'store_true')
    parser.add_argument('-m', dest='model',   help='Use predictions from model' ,default = 'keras')
    args = parser.parse_args()

    print "---------------------------------"
    print "Collecting {0} events".format(args.channel)
    print "Using prediction from {0}".format(args.model)
    print "Writing {0} to datacard".format( args.var )
    if args.all:
        print "Add shape templates in datacard"
    print "---------------------------------"

    read = Reader(channel=args.channel,
                  config_file = "conf/scale_samples.json",
                  folds = 2)

    C = Collector(channel = args.channel, 
                  target_names = read.config["target_names"],
                  path = args.model,
                  rebin = False )

    C.createDC(args.var, args.all)

    P = Plotter( channel = args.channel,
                 naming = read.processes,
                 path = args.model )

    P.makePlots()
    P.combineImages( )

class Collector():

    def __init__(self, channel , target_names={}, path = "", recreate = False, rebin = False):
        self.channel = channel
        self.rebin = rebin
        self.predictionPath = "/".join(["predictions",path, channel])

        if recreate and os.path.exists(self.predictionPath ):
            print "Replacing predictions in {0} {1}".format(channel, path)
            shutil.rmtree( self.predictionPath  )

        if not os.path.exists(self.predictionPath ):
            os.makedirs(self.predictionPath )

        if not os.path.exists(path):
            os.mkdir(path)

        if path:  self.filename = "/".join([path, "htt_"+channel+".inputs-sm-13TeV-ML.root"])
        else:     self.filename = "htt_"+channel+".inputs-sm-13TeV-ML.root"

        if target_names:  self.target_names = {int(k):v for k,v in target_names.items()}
        else:             self.target_names = target_names

        self.createDCFile()

        with open("conf/reweighting.json","r") as FSO:
            self.reweight = json.load(FSO)

        self.binning = {
            "pred_prob": {"def": (8, array("d", [0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0] ) )},
            "eta_1":     {"def": (30,-3,3)},
            "iso_1":     {"def": (100,0,1)},
            "iso_2":     {"def": (100,0,1)},
            "eta_2":     {"def": (50,-2.3,2.3)},
            "pt_1":      {"def": (100,20,220)},
            "pt_2":      {"def": (100,20,220)},
            "jpt_1":     {"def": (100,-10,220)},
            "jpt_2":     {"def": (100,-10,220)},
            "jm_1":      {"def": (100,-10,100)},
            "jm_2":      {"def": (100,-10,100)},
            "jphi_1":    {"def": (100,-10,5)},
            "jphi_2":    {"def": (100,-10,5)},
            "bpt_1":     {"def": (100,-10,220)},
            "bpt_2":     {"def": (100,-10,220)},
            "bcsv_1":    {"def": (100,0,1)},
            "bcsv_2":    {"def": (100,0,1)},
            "beta_1":    {"def": (100,-10,2.5)},
            "beta_2":    {"def": (100,-10,2.5)},
            "njets":     {"def": (12,0,12)},
            "nbtag":     {"def": (12,0,12)},
            "mt_1":      {"def": (100,0,100)},
            "mt_2":      {"def": (100,0,150)},
            "pt_tt":     {"def": (100,0,150)},
            "m_sv":      {"def": (30,0,300)},
            "m_vis":     {"def": (30,0,300)},
            "mjj":       {"def": (100,-10,150)},
            "met":       {"def": (100,0,150)},
            "dzeta":     {"def": (100,-100,150)}
        }
        if rebin:
            self.binning["pred_prob"] = {"def": (8, array("d", [0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0] ) ), 
                                         "ggH": (100,0.2, 1.0  ),
                                         "qqH": (100,0.2, 1.0  )}

    def __del__(self):
        if self.DCfile and not self.FileClosed:
            self.DCfile.Close()

    def createDCFile(self):
        self.FileClosed = False
        self.DCfile =  R.TFile(self.filename,"RECREATE")

        for name in self.target_names.values():
            self.DCfile.mkdir( self.d(name) )

    def d(self, target):
        return "_".join([self.channel, target]) 

    def addPrediction(self, prediction, df, sample):
        for i in xrange( len(df) ):

            df[i]["pred_prob"] =  prediction[i]["predicted_prob"]
            df[i]["pred_class"] = prediction[i]["predicted_class"]
            if sample == "ZTT":
                df[i]["event_weight"] *= 0.95
            if i == 0: mode = "w"
            else: mode = "a"
            df[i].to_root("{0}/{1}.root".format(self.predictionPath, sample), key="TauCheck", mode = mode)

    def createDC(self, var, writeAll = True, abs_path = ""):
        if not self.DCfile or self.FileClosed:
            print "Where should I write?"
            return


        path = self.predictionPath + "/"
        if abs_path: path = "/".join([abs_path,path])
        files = os.listdir( path )

        shapes   = [ path+s for s in files if "_CMS_" in s]
        looseMC  = [ path+s for s in files if not "_CMS_" in s and ("_more" in s or "estimate" in s) ]
        nominal  = [ path+s for s in files if not "_CMS_" in s and not "_more" in s and not "estimate" in s]


        self.writeTemplates(var, nominal, writeAll)
        self.estimateQCD(var, looseMC, writeAll)
        if writeAll:
            self.writeTemplates(var, shapes)

        self.DCfile.Close()
        self.FileClosed = True

        if self.rebin:
            print "Start rebinning"
            self.setRebinning()
            self.createDCFile()

            self.writeTemplates(var, nominal, writeAll)
            self.estimateQCD(var, looseMC, writeAll)
            if writeAll:
                self.writeTemplates(var, shapes)

            self.DCfile.Close()
            self.FileClosed = True




    def setRebinning(self):
        DC = R.TFile( self.filename, "READ" )

        Dirs = {"ggH": DC.Get(self.channel + "_ggH"), "qqH":DC.Get(self.channel + "_qqH") }

        sig = ["ggH125", "qqH125"]
        bkg = ["TTT","TTJ","ZTT","ZL","ZJ","VVT","VVJ","W","QCD","EWKZ"]

        Hists = {}
        for Dir in Dirs:
            Hists[Dir] = {"s":R.TList(),"b":R.TList()}
            for hist in Dirs[Dir].GetListOfKeys():
                hname = hist.GetName()

                if hname in sig:
                    Hists[Dir]["s"].Add( copy.deepcopy( Dirs[Dir].Get( hname )  ) )
                elif hname in bkg:
                    Hists[Dir]["b"].Add( copy.deepcopy( Dirs[Dir].Get( hname )  ) )

            for h in ["s","b"]:
                tmp = copy.deepcopy( Hists[Dir][h][0] )
                tmp.Reset()
                tmp.Merge( Hists[Dir][h] )
                Hists[Dir][h] = copy.deepcopy( tmp ) 

            self.binning["pred_prob"][Dir] = rebin( Hists[Dir]["s"], Hists[Dir]["b"] )

        DC.Close()


    def writeTemplates(self, var, templates, reweight = False):
        for template in templates:
            histname = template.split("/")[-1].replace(".root","")
            templ_content = rp.read_root( paths = template )
            if var == "pred_prob":
                templ_content[var].replace(1.0,0.9999, inplace = True)

            classes = np.unique( templ_content["pred_class"] )
            for c in classes:

                binning = self.binning[var].get( self.target_names[int(c)], self.binning[var]["def"] )
                tmpCont = templ_content.query( "pred_class == {0}".format(int(c)) )

                tmpHist = R.TH1D(histname,histname,*binning )
                tmpHist.Sumw2()
                rn.fill_hist( tmpHist, array = tmpCont[var].values,
                              weights = tmpCont["event_weight"].values )

                self.DCfile.cd( self.d( self.target_names[int(c)] ) )

                tmpHist.Write()

                if reweight:
                    for rw in self.reweight:
                        rwname = rw.replace("reweight",histname).replace("CHAN",self.channel).replace("CAT", self.target_names[int(c)] )
                        tmpHist = R.TH1D(rwname,rwname,*binning)
                        rn.fill_hist( tmpHist, array = tmpCont[var].values,
                                      weights = tmpCont.eval( self.reweight[rw] ).values )
                        tmpHist.Write()


    def estimateQCD(self, var, looseMC, reweight = False):
        with open("conf/cuts.json","r") as FSO:
            cuts = json.load(FSO)

        if self.channel != "tt":

            for c,t in self.target_names.items():
                binning = self.binning[var].get(t, self.binning[var]["def"] )

                tmpQCD = R.TH1D("QCD","QCD",*binning)

                for i,template in enumerate(looseMC):
                    if "data" in template: continue 

                    tmpHist = R.TH1D("QCD"+str(i), "QCD"+str(i), *binning)
                    tmpHist.Sumw2()
                    templ_content = rp.read_root( paths  = template,
                                                  where = "pred_class == {0}".format(int(c)) )

                    if var == "pred_prob":
                        templ_content[var].replace(1.0,0.9999, inplace = True)

                    rn.fill_hist( tmpHist, array = templ_content[var].values,
                                  weights = templ_content["event_weight"].values )

                    if "estimate" in template: tmpQCD.Add(tmpHist)
                    else:                  tmpQCD.Add(tmpHist, -1)

                self.DCfile.cd( self.d( t ) )
                if reweight:
                    for rw in ["QCD_WSFUncert_{chan}_{cat}_13TeVUp","QCD_WSFUncert_{chan}_{cat}_13TeVDown"]:
                        rwname = rw.format( chan = self.channel, cat = t )
                        tmp = copy.deepcopy( tmpQCD )
                        tmp.SetName(rwname)
                        tmp.Write()

                tmpQCD.Write()
        else:


            for c,t in self.target_names.items():

                binning = self.binning[var].get(t, self.binning[var]["def"] )

                tmpHists = { "-ISO-":    {"-SS-": R.TH1D("ssiso"+t,"ssiso"+t,*binning),   "-OS-": R.TH1D("osiso"+t,"osiso"+t,*binning)},
                             "-ANTIISO-":{"-SS-": R.TH1D("ssaiso"+t,"ssaiso"+t,*binning), "-OS-": R.TH1D("osaiso"+t,"osaiso"+t,*binning)} 
                            }

                for i,template in enumerate(looseMC):

                    for iso in tmpHists:
                        for sign in tmpHists[iso]:
                            if sign == "-SS-" and "estimate" in template: continue
                            if sign == "-OS-":
                                if "data" in template: continue
                                if iso == "-ISO-" and "estimate" in template: continue

                            tmpHist =  R.TH1D(sign+str(i)+iso, sign+str(i)+iso, *binning)
                            try:
                                templ_content = rp.read_root( paths  = template,
                                                              where = "pred_class == {0} && {1} && {2}".format(int(c), cuts[iso]["tt"], cuts[sign]  ) )
                            except IndexError:
                                pass
                            rn.fill_hist( tmpHist, array = templ_content[var].values,
                                          weights = templ_content["event_weight"].values )

                            if "data" in template or "estimate" in template: addV = 1
                            else: addV = -1
                            tmpHists[iso][sign].Add(tmpHist, addV)

                tmpHists["-ANTIISO-"]["-OS-"].Scale( tmpHists["-ISO-"]["-SS-"].Integral() / float(tmpHists["-ANTIISO-"]["-SS-"].Integral() ) )
                tmpHists["-ANTIISO-"]["-OS-"].SetName("QCD")

                self.DCfile.cd( self.d( t ) )
                if reweight:
                    for rw in ["QCD_WSFUncert_{chan}_{cat}_13TeVUp","QCD_WSFUncert_{chan}_{cat}_13TeVDown"]:
                        rwname = rw.format( chan = self.channel, cat = t )
                        tmp = copy.deepcopy( tmpHists["-ANTIISO-"]["-OS-"] )
                        tmp.SetName(rwname)
                        tmp.Write()
                tmpHists["-ANTIISO-"]["-OS-"].Write()



def rebin(m_sig, m_bg):
    #    const float RELSTATMAX=0.5
    RELSTATMAX=float(0.2)
    BINC=float(1.4)

    bin_edge = np.array([])
    
    nedges = int( m_sig.GetNbinsX()+1 ) #edges=bins+1
    bin_edge = [ float( m_sig.GetBinLowEdge( nedges ) ) ]

    bprev=0
    b=0
    s=0
    serr2=0
    berr2=0
    for i in reversed(xrange(1,nedges-1)): #loop over bin edges


        s += m_sig.GetBinContent(i)
        serr2 += m_sig.GetBinError(i)**2

        b += m_bg.GetBinContent(i)
        berr2 += m_bg.GetBinError(i)**2

        # t_edge=m_sig.GetBinLowEdge( i )
        #check if this is a new edge
        if ( b<1e-3 ): continue #if b is negativ or 0 or very small, continue
        if ( (np.sqrt(berr2)/b)>RELSTATMAX ): continue #if the rel stat unc on the background is >X%, continue
        if ( b<bprev*BINC ): continue #more b than bin to the right (previous bin)


        # if ( t_edge<0.8 ):
        #     if ( bin_edge[-1]-t_edge < 0.05 ): continue
        # if ( t_edge<0.6 ):
        #     if ( bin_edge[-1]-t_edge < 0.10 ): continue
        # if ( t_edge<0.4 ):
        #     if ( bin_edge[-1]-t_edge < 0.20 ): continue

        #we have a new edge!
        bin_edge.append( m_sig.GetBinLowEdge( i ) )
       
        bprev=b
        b=0
        s=0
        serr2=0
        berr2=0

    if bin_edge[-1] > 0.2: bin_edge[-1] = 0.2
    # bin_edge.append( 0.2 )

    bin_edge = array("d",bin_edge[::-1])

    return ( len(bin_edge)-1, bin_edge )





if __name__ == '__main__':
    main()
