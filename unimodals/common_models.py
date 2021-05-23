import torch
from torch import nn
from torch.nn import functional as F
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence
from torchvision import models as tmodels


class Linear(torch.nn.Module):
    def __init__(self,indim,outdim):
        super(Linear, self).__init__()
        self.fc = nn.Linear(indim,outdim)
    def forward(self,x,training=False):
        return self.fc(x)


class Squeeze(torch.nn.Module):
    def __init__(self, dim=None):
        super().__init__()
        self.dim = dim

    def forward(self, x, training=False):
        if self.dim is None:
            return torch.squeeze(x)
        else:
            return torch.squeeze(x, self.dim)


class MLP(torch.nn.Module):
    def __init__(self, indim, hiddim, outdim, dropout=False,dropoutp=0.1,output_each_layer=False):
        super(MLP, self).__init__()
        self.fc = nn.Linear(indim,hiddim)
        self.fc2 = nn.Linear(hiddim,outdim)
        self.dropoutp = dropoutp
        self.dropout = dropout
        self.output_each_layer = output_each_layer
        self.lklu = nn.LeakyReLU(0.2)
    def forward(self, x, training=True):
        output = F.relu(self.fc(x))
        if self.dropout:
            output = F.dropout(output,p=self.dropout,training=training)
        output2 = self.fc2(output)
        if self.dropout:
            output2 = F.dropout(output,p=self.dropoutp,training=training)
        if self.output_each_layer:
            return [0,x,output,self.lklu(output2)]
        return output2


class GRU(torch.nn.Module):
    def __init__(self,indim,hiddim,dropout=False,dropoutp=0.1,flatten=False,has_padding=False):
        super(GRU,self).__init__()
        self.gru=nn.GRU(indim,hiddim)
        self.dropoutp=dropoutp
        self.dropout=dropout
        self.flatten=flatten
        self.has_padding=has_padding
    def forward(self,x,training=True):
        if self.has_padding:
            x = pack_padded_sequence(x[0],x[1],batch_first=True,enforce_sorted=False)
            out=self.gru(x)[1][-1]
        else:
            out=self.gru(x)[0]
        if self.dropout:
            out = F.dropout(out,p=self.dropoutp,training=training)
        if self.flatten:
            out=torch.flatten(out,1)
        return out


class GRUWithLinear(torch.nn.Module):
    def __init__(self,indim,hiddim,outdim,dropout=False,dropoutp=0.1,flatten=False,has_padding=False,output_each_layer=False):
        super(GRUWithLinear,self).__init__()
        self.gru=nn.GRU(indim,hiddim)
        self.linear = nn.Linear(hiddim,outdim)
        self.dropoutp=dropoutp
        self.dropout=dropout
        self.flatten=flatten
        self.has_padding=has_padding
        self.output_each_layer = output_each_layer
        self.lklu = nn.LeakyReLU(0.2)
    def forward(self,x,training=True):
        if self.has_padding:
            x = pack_padded_sequence(x[0],x[1],batch_first=True,enforce_sorted=False)
            hidden=self.gru(x)[1][-1]
        else:
            hidden=self.gru(x)[0]
        if self.dropout:
            hidden = F.dropout(hidden,p=self.dropoutp,training=training)
        out = self.linear(hidden)
        if self.flatten:
            out=torch.flatten(out,1)
        if self.output_each_layer:
            return [0,torch.flatten(x,1),torch.flatten(hidden,1),self.lklu(out)]
        return out


class LSTM(torch.nn.Module):
    def __init__(self,indim,hiddim,dropout=False,dropoutp=0.1,flatten=False,has_padding=False):
        super(LSTM,self).__init__()
        self.lstm=nn.LSTM(indim,hiddim,batch_first=True)
        self.dropoutp=dropoutp
        self.dropout=dropout
        self.flatten=flatten
        self.has_padding=has_padding
    def forward(self,x,training=True):
        if self.has_padding:
            x = pack_padded_sequence(x[0],x[1],batch_first=True,enforce_sorted=False)
            out=self.lstm(x)[1][0]
        else:
            if len(x.size()) == 2:
                x = x.unsqueeze(2)
            out=self.lstm(x)[1][0]
        out = out.permute([1, 2, 0])
        out = out.reshape([out.size()[0], -1])
        if self.dropout:
            out = F.dropout(out,p=self.dropoutp,training=training)
        if self.flatten:
            out=torch.flatten(out,1)
        return out


class TwoLayersLSTM(torch.nn.Module):
    def __init__(self, indim, hiddim, dropout=False, dropoutp=0.1, flatten=False, has_padding=False,
                 LayNorm=True, isBidirectional=True):
        super(TwoLayersLSTM, self).__init__()
        self.lstm_0 = nn.LSTM(indim, hiddim, batch_first=True, bidirectional=isBidirectional)
        self.lstm_1 = nn.LSTM(2*indim, hiddim, batch_first=True, bidirectional=isBidirectional)
        self.layer_norm = nn.LayerNorm(2*hiddim)
        self.dropoutp = dropoutp
        self.dropout = dropout
        self.flatten = flatten
        self.has_padding = has_padding
        self.LayerNorm = LayNorm

    def forward(self, x, training=True):
        if self.has_padding:
            x = pack_padded_sequence(x[0], x[1], batch_first=True, enforce_sorted=False)
            out = self.lstm(x)[1][-1]

            packed_sequence = pack_padded_sequence(x[0], x[1])
            packed_h1, (final_h1, _) = self.lstm_0(packed_sequence)
            padded_h1, _ = pad_packed_sequence(packed_h1)
            normed_h1 = self.layer_norm(padded_h1)
            packed_normed_h1 = pack_padded_sequence(normed_h1, x[1])
            _, (out, _) = self.lstm_1(packed_normed_h1)
        else:
            out = self.lstm_0(x)[0]
            out = self.lstm_1(out)[0]
        if self.dropout:
            out = F.dropout(out, p=self.dropoutp, training=training)
        if self.flatten:
            out = torch.flatten(out, 1)
        return out


class LSTMWithLinear(torch.nn.Module):
    def __init__(self,indim,hiddim,outdim,dropout=False,dropoutp=0.1,flatten=False,has_padding=False):
        super(LSTMWithLinear,self).__init__()
        self.lstm = nn.LSTM(indim, hiddim, batch_first=True)
        self.linear = nn.Linear(hiddim, outdim)
        self.dropoutp=dropoutp
        self.dropout=dropout
        self.flatten=flatten
        self.has_padding=has_padding
    def forward(self,x,training=True):
        if self.has_padding:
            x = pack_padded_sequence(x[0],x[1],batch_first=True,enforce_sorted=False)
            hidden=self.lstm(x)[1][0]
        else:
            if len(x.size()) == 2:
                x = x.unsqueeze(2)
            hidden=self.lstm(x)[1][0]
        hidden = hidden.permute([1, 2, 0])
        hidden = hidden.reshape([hidden.size()[0], -1])
        if self.dropout:
            hidden = F.dropout(hidden,p=self.dropoutp,training=training)
        out = self.linear(hidden)
        return out


#adapted from centralnet code https://github.com/slyviacassell/_MFAS/blob/master/models/central/avmnist.py
class LeNet(nn.Module):
    def __init__(self,in_channels,args_channels,additional_layers,output_each_layer=False,linear=None,squeeze_output=True):
        super(LeNet,self).__init__()
        self.output_each_layer=output_each_layer
        self.convs=[nn.Conv2d(in_channels,args_channels,kernel_size=5,padding=2,bias=False)]
        self.bns=[nn.BatchNorm2d(args_channels)]
        self.gps=[GlobalPooling2D()]
        for i in range(additional_layers):
            self.convs.append(nn.Conv2d((2**i)*args_channels,(2**(i+1))*args_channels,kernel_size=3,padding=1,bias=False))
            self.bns.append(nn.BatchNorm2d(args_channels*(2**(i+1))))
            self.gps.append(GlobalPooling2D())
        self.convs=nn.ModuleList(self.convs)
        self.bns=nn.ModuleList(self.bns)
        self.gps=nn.ModuleList(self.gps)
        self.sq_out=squeeze_output
        self.linear=None
        if linear is not None:
            self.linear=nn.Linear(linear[0],linear[1])
        for m in self.modules():
            if isinstance(m, (nn.Conv2d, nn.Linear)):
                nn.init.kaiming_uniform_(m.weight)
    def forward(self,x,training=False):
        tempouts=[]
        out=x
        for i in range(len(self.convs)):
            out=F.relu(self.bns[i](self.convs[i](out)))
            out=F.max_pool2d(out,2)
            gp=self.gps[i](out)
            tempouts.append(gp)
            #print(out.size())
        if self.linear is not None:
            out=self.linear(out)
        tempouts.append(out)
        if self.output_each_layer:
            if self.sq_out:
                return [t.squeeze() for t in tempouts]
            return tempouts
        if self.sq_out:
            return out.squeeze()
        return out


class VGG16(nn.Module):
    def __init__(self, hiddim, pretrained=True):
        super(VGG16, self).__init__()
        self.hiddim = hiddim
        self.model = tmodels.vgg16_bn(pretrained=pretrained)
        self.model.classifier[6] = nn.Linear(4096, hiddim)

    def forward(self, x, training=False):
        return self.model(x)

class VGG16Slim(nn.Module): # slimmer version of vgg16 model with fewer layers in classifier
    def __init__(self, hiddim, dropout=True, dropoutp=0.2, pretrained=True):
        super(VGG16Slim, self).__init__()
        self.hiddim = hiddim
        self.model = tmodels.vgg16_bn(pretrained=pretrained)
        self.model.classifier = nn.Linear(512 * 7 * 7, hiddim)
        if dropout:
            feats_list = list(self.model.features)
            new_feats_list = []
            for feat in feats_list:
                new_feats_list.append(feat)
                if isinstance(feat, nn.ReLU):
                    new_feats_list.append(nn.Dropout(p=dropoutp))

            self.model.features = nn.Sequential(*new_feats_list)

    def forward(self, x, training=False):
        return self.model(x)

class VGG11Slim(nn.Module): # slimmer version of vgg11 model with fewer layers in classifier
    def __init__(self, hiddim, dropout=True, dropoutp=0.2, pretrained=True):
        super(VGG11Slim, self).__init__()
        self.hiddim = hiddim
        self.model = tmodels.vgg11_bn(pretrained=pretrained)
        self.model.classifier = nn.Linear(512 * 7 * 7, hiddim)
        if dropout:
            feats_list = list(self.model.features)
            new_feats_list = []
            for feat in feats_list:
                new_feats_list.append(feat)
                if isinstance(feat, nn.ReLU):
                    new_feats_list.append(nn.Dropout(p=dropoutp))

            self.model.features = nn.Sequential(*new_feats_list)

    def forward(self, x, training=False):
        return self.model(x)

class VGG(nn.Module):
    def __init__(self, num_outputs):
        super(VGG, self).__init__()

        # self.vgg = tmodels.vgg19(pretrained='imagenet')
        vgg = list(tmodels.vgg19(pretrained='imagenet').features)
        self.vgg = nn.ModuleList(vgg)
        self.gp1 = GlobalPooling2D()
        self.gp2 = GlobalPooling2D()
        self.gp3 = GlobalPooling2D()
        self.gp4 = GlobalPooling2D()

        self.bn4 = nn.BatchNorm1d(512)  # only used for classifier

        self.classifier = nn.Linear(512, num_outputs)

    def forward(self, x):

        for i_l, layer in enumerate(self.vgg):

            x = layer(x)

            if i_l == 20:
                out_1 = self.gp1(x)

            if i_l == 26:
                out_2 = self.gp2(x)

            if i_l == 33:
                out_3 = self.gp3(x)

            if i_l == 36:
                out_4 = self.gp4(x)
                bn_4 = self.bn4(out_4)

        out = self.classifier(bn_4)

        # print()
        # print(out_4, out)

        return out_1, out_2, out_3, out_4, out


class Maxout(nn.Module):
    def __init__(self, d, m, k):
        super(Maxout, self).__init__()
        self.d_in, self.d_out, self.pool_size = d, m, k
        self.lin = nn.Linear(d, m * k)

    def forward(self, inputs):
        shape = list(inputs.size())
        shape[-1] = self.d_out
        shape.append(self.pool_size)
        max_dim = len(shape) - 1
        out = self.lin(inputs)
        m, i = out.view(*shape).max(dim=max_dim)
        return m


class MaxOut_MLP(nn.Module):

    def __init__(self, num_outputs, first_hidden=64, number_input_feats=300):
        super(MaxOut_MLP, self).__init__()

        self.op1 = Maxout(number_input_feats, first_hidden, 5)
        self.op2 = nn.Sequential(nn.BatchNorm1d(first_hidden), nn.Dropout(0.5))
        self.op3 = Maxout(first_hidden, first_hidden * 2, 5)
        self.op4 = nn.Sequential(nn.BatchNorm1d(first_hidden * 2), nn.Dropout(0.5))

        # The linear layer that maps from hidden state space to output space
        self.hid2val = nn.Linear(first_hidden * 2, num_outputs)

    def forward(self, x):
        o1 = self.op1(x)
        o2 = self.op2(o1)
        o3 = self.op3(o2)
        o4 = self.op4(o3)
        o5 = self.hid2val(o4)

        return o1, o3, o5


class GlobalPooling2D(nn.Module):
    def __init__(self):
        super(GlobalPooling2D, self).__init__()

    def forward(self, x):
        # apply global average pooling
        x = x.view(x.size(0), x.size(1), -1)
        x = torch.mean(x, 2)
        x = x.view(x.size(0), -1)

        return x


class Constant(nn.Module):
    def __init__(self,out_dim):
        super(Constant,self).__init__()
        self.out_dim=out_dim
    def forward(self,x,training=False):
        return torch.zeros(self.out_dim).cuda()


class Identity(nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self, x, training=False):
        return x


# deep averaging network: https://people.cs.umass.edu/~miyyer/pubs/2015_acl_dan.pdf
# deep sets: https://arxiv.org/abs/1703.06114
class DAN(torch.nn.Module):
    def __init__(self, indim, hiddim, dropout=False, dropoutp=0.25, nlayers=3, has_padding=False):
        super(DAN, self).__init__()
        self.dropoutp = dropoutp
        self.dropout = dropout
        self.nlayers = nlayers
        self.has_padding = has_padding

        self.embedding = nn.Linear(indim, hiddim)

        mlp = []
        for _ in range(nlayers):
            mlp.append(nn.Linear(hiddim, hiddim))
        self.mlp = nn.ModuleList(mlp)

    def forward(self, x, training=True):
        # x_vals: B x S x P
        if self.has_padding:
            x_vals = x[0]
            x_lens = x[1]
        else:
            x_vals = x
        # embedded: B x S x H
        embedded = self.embedding(x_vals)
        if self.dropout:
            embedded = F.dropout(embedded, p=self.dropoutp, training=training)
        if self.has_padding:
            # mask out padded values
            # mask: B x S
            mask = torch.arange(embedded.shape[1], device=embedded.device).repeat(embedded.shape[0], 1) < x_lens.repeat(-1, 1).repeat(1, embedded.shape[1])
            embedded[~mask] = 0
        # sum pooling
        # pool: B x H
        pooled = embedded.sum(dim=1)
        for layer in self.mlp:
            pooled = layer(pooled)
            if self.dropout:
                pooled = F.dropout(pooled, p=self.dropoutp, training=training)
        return pooled
