import numpy as np
import cudarray as ca
from ..base import Model, CollectionMixin
from ..expr.base import UnaryElementWise
from ..input import Input
from .. import expr


class NegativeGradient(UnaryElementWise):
    def fprop(self):
        self.out = self.x.out

    def bprop(self):
        ca.negative(self.out_grad, self.x.out_grad)


class AdversarialNet(Model, CollectionMixin):
    def __init__(self, generator, discriminator, n_hidden):
        self.generator = generator
        self.discriminator = discriminator
        self.n_hidden = n_hidden
        self.eps = 1e-4
        self.collection = [generator, discriminator]

    def setup(self, x_shape):
        batch_size = x_shape[0]
        self.x_src = expr.Source(x_shape)
        z = expr.random.normal(size=(batch_size, self.n_hidden))
        x_tilde = self.generator(z)
        x_tilde = NegativeGradient()(x_tilde)
        x = expr.Concatenate(axis=0)(self.x_src, x_tilde)
        d = self.discriminator(x)
        d = expr.clip(d, self.eps, 1.0-self.eps)
        sign = np.ones((batch_size*2, 1), dtype=ca.float_)
        sign[batch_size:] = -1.0
        offset = np.zeros_like(sign)
        offset[batch_size:] = 1.0
        self._loss = expr.log(d*sign + offset)
        self._graph = expr.ExprGraph(-expr.sum(self._loss))
        self._graph.out_grad = ca.array(1.0)
        self._graph.setup()

    @property
    def params(self):
        return self.generator.params, self.discriminator.params

    def update(self, x):
        self.x_src.out = x
        self._graph.fprop()
        self._graph.bprop()
        gan_loss = -np.array(self._loss.out)
        batch_size = x.shape[0]
        d_x_loss = np.mean(gan_loss[:batch_size])
        d_z_loss = np.mean(gan_loss[batch_size:])
        return float(d_x_loss), float(d_z_loss)

    def generate(self, hidden):
        """ Hidden to input. """
        self.phase = 'test'
        input = Input.from_any(hidden)
        z_src = expr.Source(input.x_shape)
        graph = expr.ExprGraph(self.generator(z_src))
        graph.setup()
        x_tilde = []
        for z_batch in input.batches():
            z_src.out = z_batch['x']
            graph.fprop()
            x_tilde.append(np.array(graph.out))
        x_tilde = np.concatenate(x_tilde)[:input.n_samples]
        return x_tilde
