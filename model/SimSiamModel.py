# -*- coding: utf-8 -*-
# MIT License
#
# Copyright (c) 2017 Kai Arulkumaran
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# ==============================================================================
from __future__ import division
import math
import torch
from torch import nn
from torch.nn import functional as F


# Factorised NoisyLinear layer with bias
class NoisyLinear(nn.Module):
  def __init__(self, in_features, out_features, std_init=0.5):
    super(NoisyLinear, self).__init__()
    self.module_name = 'noisy_linear'
    self.in_features = in_features
    self.out_features = out_features
    self.std_init = std_init
    self.weight_mu = nn.Parameter(torch.empty(out_features, in_features))
    self.weight_sigma = nn.Parameter(torch.empty(out_features, in_features))
    self.register_buffer('weight_epsilon', torch.empty(out_features, in_features))
    self.bias_mu = nn.Parameter(torch.empty(out_features))
    self.bias_sigma = nn.Parameter(torch.empty(out_features))
    self.register_buffer('bias_epsilon', torch.empty(out_features))
    self.reset_parameters()
    self.reset_noise()

  def reset_parameters(self):
    mu_range = 1 / math.sqrt(self.in_features)
    self.weight_mu.data.uniform_(-mu_range, mu_range)
    self.weight_sigma.data.fill_(self.std_init / math.sqrt(self.in_features))
    self.bias_mu.data.uniform_(-mu_range, mu_range)
    self.bias_sigma.data.fill_(self.std_init / math.sqrt(self.out_features))

  def _scale_noise(self, size):
    x = torch.randn(size)
    return x.sign().mul_(x.abs().sqrt_())

  def reset_noise(self):
    epsilon_in = self._scale_noise(self.in_features)
    epsilon_out = self._scale_noise(self.out_features)
    self.weight_epsilon.copy_(epsilon_out.ger(epsilon_in))
    self.bias_epsilon.copy_(epsilon_out)

  def forward(self, input):
    if self.training:
      return F.linear(input, self.weight_mu + self.weight_sigma * self.weight_epsilon, self.bias_mu + self.bias_sigma * self.bias_epsilon)
    else:
      return F.linear(input, self.weight_mu, self.bias_mu)

class MLP_projection(nn.Module):
  def __init__(self, input_dim, output_dim=128, hidden_dim=256):
    super(MLP_projection, self).__init__()
    self.layer1 = nn.Sequential(
      nn.Linear(input_dim, hidden_dim),
      # nn.BatchNorm1d(hidden_dim),
      nn.ReLU(inplace=True)
    )
    self.layer2 = nn.Sequential(
      nn.Linear(hidden_dim, hidden_dim),
      # nn.BatchNorm1d(hidden_dim),
      nn.ReLU(inplace=True)
    )
    self.layer3 = nn.Sequential(
      nn.Linear(hidden_dim, output_dim),
      # nn.BatchNorm1d(output_dim),
    )
    self.num_layers = 3
  
  def set_layers(self, layers):
    self.num_layers = layers
      
  def forward(self, x):
    if self.num_layers == 3:
      x = self.layer1(x)
      x = self.layer2(x)
      x = self.layer3(x)
    elif self.num_layers == 2:
      x = self.layer1(x)
      x = self.layer3(x)
    else:
      raise ValueError(f"layer num must be 2 or 3, {self.num_layers} is not supported")
    return x
    
class MLP_prediction(nn.Module):
  def __init__(self, input_dim, output_dim=128, hidden_dim=256):
    super(MLP_prediction, self).__init__()
    self.layer1 = nn.Sequential(
      nn.Linear(input_dim, hidden_dim),
      # nn.BatchNorm1d(hidden_dim),
      nn.ReLU(inplace=True)
    )
    self.layer2 = nn.Linear(hidden_dim, output_dim)
    
  def forward(self, x):
    x = self.layer1(x)
    x = self.layer2(x)
    return x

class DQN(nn.Module):
  def __init__(self, args, action_space):
    super(DQN, self).__init__()
    self.atoms = args.atoms
    self.action_space = action_space

    if args.architecture == 'canonical':
      self.convs = nn.Sequential(nn.Conv2d(args.history_length, 32, 8, stride=4, padding=0), nn.ReLU(),
                                 nn.Conv2d(32, 64, 4, stride=2, padding=0), nn.ReLU(),
                                 nn.Conv2d(64, 64, 3, stride=1, padding=0), nn.ReLU())
      self.conv_output_size = 3136
    elif args.architecture == 'data-efficient':
      self.convs = nn.Sequential(nn.Conv2d(args.history_length, 32, 5, stride=5, padding=0), nn.ReLU(),
                                 nn.Conv2d(32, 64, 5, stride=5, padding=0), nn.ReLU())
      self.conv_output_size = 576
    self.fc_h_v = NoisyLinear(self.conv_output_size, args.hidden_size, std_init=args.noisy_std)
    self.fc_h_a = NoisyLinear(self.conv_output_size, args.hidden_size, std_init=args.noisy_std)
    self.fc_z_v = NoisyLinear(args.hidden_size, self.atoms, std_init=args.noisy_std)
    self.fc_z_a = NoisyLinear(args.hidden_size, action_space * self.atoms, std_init=args.noisy_std)

    self.proj = MLP_projection(self.conv_output_size, hidden_dim=args.hidden_size)
    self.pred = MLP_prediction(128, hidden_dim=args.hidden_size)

  def forward(self, x, log=False):
    x = self.convs(x)
    x = x.view(-1, self.conv_output_size)
    v = self.fc_z_v(F.relu(self.fc_h_v(x)))  # Value stream
    a = self.fc_z_a(F.relu(self.fc_h_a(x)))  # Advantage stream
    
    z = self.proj(x)
    p = self.pred(z)
       
    v, a = v.view(-1, 1, self.atoms), a.view(-1, self.action_space, self.atoms)
    q = v + a - a.mean(1, keepdim=True)  # Combine streams
    if log:  # Use log softmax for numerical stability
      q = F.log_softmax(q, dim=2)  # Log probabilities with action over second dimension
    else:
      q = F.softmax(q, dim=2)  # Probabilities with action over second dimension
    return q, (z, p)

  def reset_noise(self):
    for name, module in self.named_children():
      if 'fc' in name:
        module.reset_noise()
