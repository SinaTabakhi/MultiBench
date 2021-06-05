import sys
import os
from torch import nn
sys.path.append(os.getcwd())
from training_structures.Simple_Late_Fusion import train, test
from fusions.common_fusions import Concat, MultiplicativeInteractions2Modal
from datasets.enrico.get_data import get_dataloader
from unimodals.common_models import VGG16, VGG16Slim,DAN,Linear,MLP, VGG11Slim, VGG11Pruned
from datasets.enrico.get_data_robust import get_dataloader_robust
from robustness.all_in_one import general_train, general_test

import torch

dls, weights = get_dataloader('datasets/enrico/dataset')
traindata, validdata, _ = dls
robustdata = get_dataloader_robust('datasets/enrico/dataset')
criterion = nn.CrossEntropyLoss(weight=torch.tensor(weights)).cuda()
# encoders=[VGG16Slim(64).cuda(), DAN(4, 16, dropout=True, dropoutp=0.25).cuda(), DAN(28, 16, dropout=True, dropoutp=0.25).cuda()]
# head = Linear(96, 20)
encoders=[VGG11Slim(16, dropout=True, dropoutp=0.2, freeze_features=True).cuda(), VGG11Slim(16, dropout=True, dropoutp=0.2, freeze_features=True).cuda()]
# encoders = [DAN(4, 16, dropout=True, dropoutp=0.25).cuda(), DAN(28, 16, dropout=True, dropoutp=0.25).cuda()]
head = Linear(32, 20).cuda()

# fusion=Concat().cuda()
fusion = MultiplicativeInteractions2Modal([16, 16], 32, "matrix").cuda()

allmodules = encoders + [head, fusion]

def trainprocess(filename):
    train(encoders,fusion,head,traindata,validdata,50,optimtype=torch.optim.Adam,lr=0.0001,weight_decay=0,save=filename)

filename = general_train(trainprocess, 'enrico_mi_matrix')

def testprocess(model, testdata):
    return test(model, testdata)

general_test(testprocess, filename, robustdata)
