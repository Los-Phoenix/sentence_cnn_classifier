#!/usr/bin/python
import sys
from gensim.models import word2vec
import tensorflow as tf
import numpy as np
import cPickle
import random
import cnn_utils

def pad_sentence(sentences, w2v_size, max_length):
    np.random.seed(0)
    pad_init_value = np.random.normal(0, 0.1, w2v_size).tolist()
    for i in range(len(sentences)):
        pad_length = max_length - len(sentences[i])
        pad_list = [pad_init_value] * pad_length
        sentences[i] = sentences[i] + pad_list

def change_label_type(original_label):
    label = []
    for i in range(len(original_label)):
        if original_label[i] == 1:
            label.append([1, 0])
        else:
            label.append([0, 1])
    return label

def build_data(pos_fmatrix, neg_fmatrix, pos_label, neg_label, pos_sen, neg_sen):
    fmatrix, original_label, sen = pos_fmatrix + neg_fmatrix, pos_label + neg_label, pos_sen + neg_sen
    label = change_label_type(original_label)
    return fmatrix, label, sen

def build_and_suffle_data(pos_fmatrix, neg_fmatrix, pos_label, neg_label, pos_sen, neg_sen):
    np.random.seed(0)
    data = np.array([pos_fmatrix + neg_fmatrix, pos_label + neg_label, pos_sen + neg_sen])
    suffled_indices = np.random.permutation(np.arange(len(data[0])))
    #suffile data
    fmatrix = data[0][suffled_indices].tolist()
    original_label = data[1][suffled_indices].tolist()
    sen = data[2][suffled_indices].tolist()
    label = change_label_type(original_label)
    return fmatrix, label, sen

def weight_variable(shape):
    initial = tf.truncated_normal(shape, stddev=0.1)
    return tf.Variable(initial)

def bias_variable(shape):
    initial = tf.constant(0.1, shape=shape)
    return tf.Variable(initial)

def conv2d(x, W):
    return tf.nn.conv2d(x, W, strides=[1, 1, 1, 1], padding='VALID')

def max_pool_Nx1(x, length):
    return tf.nn.max_pool(x, ksize=[1, length, 1, 1], strides=[1, 1, 1, 1], padding='VALID')

def get_batch_rand(sentences_train, labels_train, batch_size):
    sentence_batch = []
    label_batch = []
    for i in range(batch_size):
        idx = random.randint(0, len(sentences_train) - 1)
        sentence_batch.append(sentences_train[idx])
        label_batch.append(labels_train[idx])
    return sentence_batch, label_batch

def get_batch_balanced(pos_fmatrix, neg_fmatrix, pos_label, neg_label, batch_size):
    sentence_batch = []
    label_batch = []
    limit = batch_size / 2
    for i in range(limit):
        idx = random.randint(0, len(pos_fmatrix) - 1)
        sentence_batch.append(pos_fmatrix[idx])
        label_batch.append(pos_label[idx])
    for i in range(limit):
        idx = random.randint(0, len(neg_fmatrix) - 1)
        sentence_batch.append(neg_fmatrix[idx])
        label_batch.append(neg_label[idx])
    return sentence_batch, label_batch

if __name__=="__main__":
    pos_file = sys.argv[1]
    neg_file = sys.argv[2]
    model_name = sys.argv[3]

    w2v_size = 300
    label_size = 2
    training_batch_size = 50

    #load sentence with w2v word embeddings
    pos_sen, pos_fmatrix, pos_label = cPickle.load(open(pos_file, 'r'))
    neg_sen, neg_fmatrix, neg_label = cPickle.load(open(neg_file, 'r'))

    #build and shuffle data
    max_length = max(len(s) for s in (pos_fmatrix + neg_fmatrix))
    print 'max length = ', max_length
    #sentences, labels, raw_sentences = build_data(pos_fmatrix, neg_fmatrix, pos_label, neg_label, pos_sen, neg_sen)
    sentences, labels, raw_sentences = build_and_suffle_data(pos_fmatrix, neg_fmatrix, pos_label, neg_label, pos_sen, neg_sen)
    #pad sentences to the same length
    pad_sentence(sentences, w2v_size, max_length)

    #remember to do cross valadition next time... don't say lazy
    test_size = 2000
    sentences_train, sentences_test = sentences[:-test_size], sentences[-test_size:]
    labels_train, labels_test = labels[:-test_size], labels[-test_size:]
    raw_sen_train, raw_sen_test = raw_sentences[:-test_size], raw_sentences[-test_size:]
    #sentences_train = sentences
    #labels_train = labels
    #raw_sen_train = raw_sentences

    #training
    x = tf.placeholder("float", shape=[None, max_length, w2v_size])
    y_ = tf.placeholder("float", shape=[None, label_size])

    #Convolution and Pooling
    feature_size1 = 100
    filter_list = [3, 4, 5]

    poolings = []

    for idx, filter_size in enumerate(filter_list):
        x_image = tf.reshape(x, shape=[-1, max_length, w2v_size, 1])
        W_conv1 = weight_variable([filter_size, w2v_size, 1, feature_size1])
        b_conv1 = bias_variable([feature_size1])

        h_conv1 = tf.nn.relu(conv2d(x_image, W_conv1) + b_conv1)
        h_pool1 = max_pool_Nx1(h_conv1, max_length - filter_size + 1)

    #dropout
    keep_prob = tf.placeholder("float")
    h_pool1_drop = tf.nn.dropout(h_pool1, keep_prob)


    #Readout Layer
    W_fc2 = weight_variable([feature_size1, label_size])
    b_fc2 = bias_variable([label_size])

    h_pool1_flat = tf.reshape(h_pool1_drop, [-1, 1 * 1 * feature_size1])
    y_conv = tf.nn.softmax(tf.matmul(h_pool1_flat, W_fc2) + b_fc2)

    #train
    cross_entropy = -tf.reduce_sum(y_*tf.log(y_conv))
    with tf.name_scope("train") as scope:
        train_step = tf.train.AdamOptimizer(1e-4).minimize(cross_entropy)
    with tf.name_scope("self-validate") as scope:
        correct_prediction = tf.equal(tf.argmax(y_conv,1), tf.argmax(y_,1))
        train_accuracy = tf.reduce_mean(tf.cast(correct_prediction, "float"))
        train_accuracy_summary = tf.scalar_summary("trainin accuracy", train_accuracy)
    with tf.name_scope("test") as scope:
        correct_prediction_test = tf.equal(tf.argmax(y_conv,1), tf.argmax(y_,1))
        test_accuracy = tf.reduce_mean(tf.cast(correct_prediction_test, "float"))
        test_accuracy_summary = tf.scalar_summary("test accuracy", test_accuracy)

    sess = tf.InteractiveSession()
    sess.run(tf.initialize_all_variables())

    # Merge all the summaries and write them out to /tmp/mnist_logs
    merged = tf.merge_all_summaries()
    writer = tf.train.SummaryWriter("./training_logs", sess.graph_def)
    ###

    for i in range(3000):
        batch_x, batch_y = get_batch_rand(sentences_train, labels_train, training_batch_size)
        if i % 10 == 0:
            ## mini batch accuracy
            #train_accuracy_score = train_accuracy.eval(feed_dict={x: batch_x, y_: batch_y, keep_prob: 1.0})
            #print "step %d, training accuracy %g" % (i, train_accuracy_score)
            result = sess.run([train_accuracy_summary, train_accuracy], feed_dict={x: batch_x, y_: batch_y, keep_prob: 1.0})
            writer.add_summary(result[0], i)
            print "step %d, training accuracy %g" % (i, result[1])

            ## test accuracy
            #test_accuracy_score = test_accuracy.eval(feed_dict={x: sentences_test, y_: labels_test, keep_prob: 1.0})
            #print "step %d, test accuracy %g" % (i, test_accuracy_score)
            result = sess.run([test_accuracy_summary, test_accuracy], feed_dict={x: sentences_test, y_: labels_test, keep_prob: 1.0})
            writer.add_summary(result[0], i)
            print "step %d, test accuracy %g" % (i, result[1])

        sess.run(train_step, feed_dict={x: batch_x, y_: batch_y, keep_prob: 0.5})

    tf_saver = tf.train.Saver()
    tf_saver.save(sess, model_name)

    test_accuracy_score = test_accuracy.eval(feed_dict={x: sentences_test, y_: labels_test, keep_prob: 1.0})
    print "test accuracy %g" % test_accuracy_score

    pred, ans = cnn_utils.evaluate_pr(tf, x, y_, sentences_test, labels_test, y_conv, keep_prob)