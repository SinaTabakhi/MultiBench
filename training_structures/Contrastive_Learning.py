from sklearn.metrics import accuracy_score, f1_score

import torch
from torch import nn
from torch.nn import functional as F
from torch.optim.lr_scheduler import ExponentialLR

from utils.AUPRC import AUPRC
from objective_functions.contrast import MultiSimilarityLoss
#import pdb


softmax = nn.Softmax()



class MMDL(nn.Module):
    def __init__(self,encoders,fusion,refiner,head,has_padding=False):
        super(MMDL,self).__init__()
        self.encoders = nn.ModuleList(encoders)
        self.fuse = fusion
        self.head = head
        self.refiner = refiner
        self.has_padding=has_padding
    
    def forward(self,inputs,training=False):
        outs = []
        input_num = len(inputs[0]) if self.has_padding else len(inputs)
        for i in range(input_num):    
            if self.has_padding:
                outs.append(self.encoders[i]([inputs[0][i],inputs[1][i]], training=training))
            else:
                outs.append(self.encoders[i](inputs[i], training=training))
        
        fuse = self.fuse(outs, training=training)
        logit = self.head(fuse, training=training)
        sizes = [torch.flatten(ii,start_dim=1).size(1) for ii in inputs]
        rec_features = []
        if training:
            rec_feature = self.refiner(fuse, training=training)
            curr=0
            for i in range(input_num):
                if self.has_padding:
                    if i == 0:
                        rec_features.append(rec_feature[:, :inputs[0][i].size(1)])
                    else:
                        rec_features.append(rec_feature[:, \
                            inputs[0][i-1].size(1):inputs[0][i-1].size(1)+inputs[i].size(1)])
                else:
                    if i == 0:
                        rec_features.append(rec_feature[:, :sizes[0]])
                        curr = sizes[0]
                    else:
                        rec_features.append(rec_feature[:, \
                                curr:curr+sizes[i]])
                        curr += sizes[i]
            '''
            if i == 0:
                rec_features.append(rec_feature[:, :outs[i].size(-1)])
            else:
                rec_features.append(rec_feature[:, \
                    outs[i-1].size(-1):outs[i-1].size(-1)+outs[i].size(-1)])
            '''

        return [logit, fuse, outs, rec_features]

        '''
        if classifier:
            #out = self.fuse(outs, training=training)
            return self.head(outs[1], training=training)
        else:
            out1, out2 = self.contrast(outs[0], outs[1], inputs[2])
            return out1, out2 
        '''
        '''

        out = self.fuse(outs, training=training)
        out1, out2 = self.contrast(outs[0], outs[1], inputs[2])

        return self.head(out, training=training), out1, out2    
        '''

def train(
    encoders,fusion,head,refiner,train_dataloader,valid_dataloader,total_epochs,is_packed=False,
    early_stop=False,task="multilabel",optimtype=torch.optim.RMSprop,lr=0.001,weight_decay=0.0,
    criterion=nn.L1Loss(),auprc=False,save='best.pt',num_classes=10):
    
    #n_data = len(train_dataloader.dataset)
    model = MMDL(encoders,fusion,refiner,head,is_packed).cuda()
    op = optimtype(model.parameters(),lr=lr,weight_decay=weight_decay)
    #scheduler = ExponentialLR(op, 0.9)
    contrast_criterion = MultiSimilarityLoss()
    ss_criterion = nn.CosineEmbeddingLoss()

    bestvalloss = 10000
    bestacc = 0
    bestf1 = 0
    patience = 0
    
    for epoch in range(total_epochs):
        totalloss = 0.0
        totals = 0
        model.train()
        
        for j in train_dataloader:
            #print([i for i in j[:-1]])
            op.zero_grad()
            if is_packed:
                with torch.backends.cudnn.flags(enabled=False):
                    out1, out2=model(
                        [[j[0][0].cuda(), j[0][2].cuda()], j[1], j[2].cuda()],training=True)
                    #print(j[-1])
                    loss1=contrast_criterion(out1)
                    loss2=contrast_criterion(out2)
                    loss = loss1+loss2
            else:
                out=model([i.float().cuda() for i in j[:-1]],training=True)
                #print(j[-1])
                if type(criterion) == torch.nn.modules.loss.BCEWithLogitsLoss:
                    loss_cl=criterion(out[0], j[-1].float().cuda())
                else:
                    loss_cl=criterion(out[0], j[-1].cuda())
                loss_contrast = contrast_criterion(out[1], F.one_hot(j[-1]).cuda())
                loss_self = 0
                for i in range(len(out[3])):
                    loss_self += ss_criterion(out[3][i], torch.flatten(j[i].float(),start_dim=1).cuda(), \
                        torch.ones(out[3][i].size(0)).cuda())
                #print(loss_cl, loss_contrast, loss_self)
                loss = loss_cl+1e-4*loss_contrast+0.1*loss_self
            totalloss += loss * len(j[-1])
            totals+=len(j[-1])
            
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 8)
            op.step()
        
        train_loss = totalloss/totals
        print("Epoch "+str(epoch)+" train loss: "+str(train_loss))

        model.eval()
        with torch.no_grad():
            totalloss = 0.0
            pred = []
            true = []
            pts = []
            for j in valid_dataloader:
                if is_packed:
                    out=model(
                        [[j[0][0].cuda(), j[0][2].cuda()], j[1], j[2].cuda()],True,training=False)
                    #out, _, _=model(
                    #    [[j[0][0].cuda(), j[0][2].cuda()], j[1], j[2].cuda()],True,training=False)
                else:
                    out,_,_,_ = model([i.float().cuda() for i in j[:-1]],training=False)
                if type(criterion) == torch.nn.modules.loss.BCEWithLogitsLoss:
                    loss=criterion(out, j[-1].float().cuda())
                else:
                    loss=criterion(out, j[-1].cuda())
                totalloss += loss*len(j[-1])
                if task == "classification":
                    pred.append(torch.argmax(out, 1))
                elif task == "multilabel":
                    pred.append(torch.sigmoid(out).round())
                true.append(j[-1])
                if auprc:
                    #pdb.set_trace()
                    sm=softmax(out[i])
                    pts.append((sm[1].item(), j[-1][i].item()))
        if pred:
            pred = torch.cat(pred, 0).cpu().numpy()
        true = torch.cat(true, 0).cpu().numpy()
        totals = true.shape[0]
        valloss=totalloss/totals
        if task == "classification":
            acc = accuracy_score(true, pred)
            print("Epoch "+str(epoch)+" valid loss: "+str(valloss)+\
                " acc: "+str(acc))
            if acc>bestacc:
                patience = 0
                bestacc=acc
                print("Saving Best")
                torch.save(model,save)
            else:
                patience += 1
            if early_stop and patience > 7:
                break
        elif task == "multilabel":
            f1_micro = f1_score(true, pred, average="micro")
            f1_macro = f1_score(true, pred, average="macro")
            print("Epoch "+str(epoch)+" valid loss: "+str(valloss)+\
                " f1_micro: "+str(f1_micro)+" f1_macro: "+str(f1_macro))
            if f1_macro>bestf1:
                patience = 0
                bestf1=f1_macro
                print("Saving Best")
                torch.save(model,save)
            else:
                patience += 1
            if early_stop and patience > 7:
                break
        elif task == "regression":
            print("Epoch "+str(epoch)+" valid loss: "+str(valloss))
            if valloss<bestvalloss:
                patience = 0
                bestvalloss=valloss
                print("Saving Best")
                torch.save(model,save)
            else:
                patience += 1
            if early_stop and patience > 7:
                break
        if auprc:
            print("AUPRC: "+str(AUPRC(pts)))
        
        #scheduler.step()


def test(
    model,test_dataloader,is_packed=False,
    criterion=nn.L1Loss(),task="multilabel",auprc=False):
    with torch.no_grad():
        totalloss = 0.0
        pred=[]
        true=[]
        pts=[]
        for j in test_dataloader:
            if is_packed:
                out=model([[i.cuda() for i in j[0]], j[1]],training=False)
            else:
                out,_,_,_ = model([i.float().cuda() for i in j[:-1]],training=False)
            if type(criterion) == torch.nn.modules.loss.BCEWithLogitsLoss:
                loss=criterion(out, j[-1].float().cuda())
            else:
                loss=criterion(out, j[-1].cuda())
            #print(torch.cat([out,j[-1].cuda()],dim=1))
            totalloss += loss*len(j[-1])
            if task == "classification":
                pred.append(torch.argmax(out, 1))
            elif task == "multilabel":
                pred.append(torch.sigmoid(out).round())
            true.append(j[-1])
            if auprc:
                #pdb.set_trace()
                sm=softmax(out, 1)
                pts += [(sm[i][1].item(), j[-1][i].item()) for i in range(j[-1].size(0))]
        if pred:
            pred = torch.cat(pred, 0).cpu().numpy()
        true = torch.cat(true, 0).cpu().numpy()
        totals = true.shape[0]
        testloss=totalloss/totals
        if auprc:
            print("AUPRC: "+str(AUPRC(pts)))
        if task == "classification":
            print("acc: "+str(accuracy_score(true, pred)))
            return accuracy_score(true, pred)
        elif task == "multilabel":
            print(" f1_micro: "+str(f1_score(true, pred, average="micro"))+\
                " f1_macro: "+str(f1_score(true, pred, average="macro")))
            return f1_score(true, pred, average="micro"), f1_score(true, pred, average="macro"), accuracy_score(true, pred)
        elif task == "regression":
            print("mse: "+str(testloss))
            return testloss
