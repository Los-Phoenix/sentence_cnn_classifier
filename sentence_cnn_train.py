#!/usr/bin/python
import sys
import cPickle
import numpy as np
import tensorflow as tf
import random
import util.cnn_utils as cu
import argparse


if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Generate feature vector for sentences')
    parser.add_argument('-pf', '--pos_file', help='positive feature vectors for training', required=True)
    parser.add_argument('-nf', '--neg_file', help='negitive feature vectors for training', required=True)
    parser.add_argument('-w2v_size', type=int, help='word2vector size (default: 300)', default=300)
    parser.add_argument('--label_size', type=int, help='how many classes? (default: 2)', default=2)
    parser.add_argument('-b', '--training_batch_size', type=int, help='size of each batch when training (default: 50)', default=50)
    parser.add_argument('-m', '--model_output', help='the trained model', required=True)
    parser.add_argument('-test_size', type=int, help='test data size for each class', default=0)
    parser.add_argument('-iterations', type=int, help='number of training iterations (default: 1000)', default=1000)
    parser.add_argument('-dropout_rate', type=float, help='droupout rate (default: 0.5)', default=0.5)
    parser.add_argument('-e', '--evaluate_per_n_batches', type=int, help='evaluate training and test accuracy per N batches (default: 50)', default=50)
    args = parser.parse_args()

    model_name = args.model_output
    w2v_size = args.w2v_size
    label_size = args.label_size
    training_batch_size = args.training_batch_size
    iterations = args.iterations
    test_size = args.test_size
    dropout_rate = args.dropout_rate
    evaluate_per_n_batches = args.evaluate_per_n_batches

    ###load sentence with w2v word embeddings
    pos_sen, pos_fmatrix, pos_label = cPickle.load(open(args.pos_file, 'r'))
    neg_sen, neg_fmatrix, neg_label = cPickle.load(open(args.neg_file, 'r'))

    ###fix the random seed
    np.random.seed(0)
    random.seed(0)
    tf.set_random_seed(0)

    ###build and shuffle data
    max_length = max(len(s) for s in (pos_fmatrix + neg_fmatrix))
    print 'max length = ', max_length
    sentences, labels, raw_sentences = cu.build_and_shuffle_data(pos_fmatrix, neg_fmatrix, pos_label, neg_label, pos_sen, neg_sen)

    ###pad sentences to the same length
    cu.pad_sentence(sentences, w2v_size, max_length)

    ###remember to do cross valadition next time... don't say lazy
    sentences_train, labels_train, raw_sen_train = [], [], []
    sentences_test, labels_test, raw_sen_test = [], [], []
    if test_size == 0:
        sentences_train, labels_train, raw_sen_train = sentences, labels, raw_sentences
    else:
        sentences_train, sentences_test = sentences[:-test_size], sentences[-test_size:]
        labels_train, labels_test = labels[:-test_size], labels[-test_size:]
        raw_sen_train, raw_sen_test = raw_sentences[:-test_size], raw_sentences[-test_size:]

    print 'Training data size: %d' % len(sentences_train)
    print 'Test data size: %d' % len(sentences_test)


    ##########################
    ### Construct the grah ###
    ##########################

    ###training data placeholder
    with tf.name_scope('feature-vectors') as scope:
        x = tf.placeholder("float", shape=[None, max_length, w2v_size])
    with tf.name_scope('labels') as scope:
        y_ = tf.placeholder("float", shape=[None, label_size])

    ###Convolution and Pooling
    feature_size1 = 100
    filter_list = [3, 4, 5]

    poolings = []

    for idx, filter_size in enumerate(filter_list):
        with tf.name_scope('conv-window-size-%d' % filter_size) as scope: 
            x_image = tf.reshape(x, shape=[-1, max_length, w2v_size, 1])
            W_conv = cu.weight_variable([filter_size, w2v_size, 1, feature_size1])
            b_conv = cu.bias_variable([feature_size1])
            h_conv = tf.nn.relu(cu.conv2d(x_image, W_conv) + b_conv)
        with tf.name_scope('pool-window-size-%d' % filter_size) as scope:
            h_pool = cu.max_pool_Nx1(h_conv, max_length - filter_size + 1)
        poolings.append(h_pool)

    ###combine pooled features
    with tf.name_scope('concat-max-pools') as scope:
        filters_total_size = feature_size1 * len(filter_list)
        h_pools = tf.concat(3, poolings)
        h_pool_all = tf.reshape(h_pools, [-1, filters_total_size])

    ###dropout
    with tf.name_scope('dropout') as scope:
        keep_prob = tf.placeholder("float")
        h_pool1_drop = tf.nn.dropout(h_pool_all, keep_prob)

    ###readout Layer
    with tf.name_scope('full-connected') as scope:
        W_fc2 = cu.weight_variable([filters_total_size, label_size])
        b_fc2 = cu.bias_variable([label_size])
        h_pool1_flat = tf.reshape(h_pool1_drop, [-1, 1 * 1 * filters_total_size])
        y_conv = tf.nn.softmax(tf.matmul(h_pool1_flat, W_fc2) + b_fc2)

    ###train
    with tf.name_scope('compute-loss') as scope:
        cross_entropy = -tf.reduce_sum(y_*tf.log(y_conv))
    with tf.name_scope('train') as scope:
        train_step = tf.train.AdamOptimizer(1e-4).minimize(cross_entropy)

    ###test
    with tf.name_scope("training-accuracy") as scope:
        correct_prediction = tf.equal(tf.argmax(y_conv,1), tf.argmax(y_,1))
        train_accuracy = tf.reduce_mean(tf.cast(correct_prediction, "float"))
        train_accuracy_summary = tf.scalar_summary("training accuracy", train_accuracy)
    with tf.name_scope("test-accuracy") as scope:
        correct_prediction_test = tf.equal(tf.argmax(y_conv,1), tf.argmax(y_,1))
        test_accuracy = tf.reduce_mean(tf.cast(correct_prediction_test, "float"))
        test_accuracy_summary = tf.scalar_summary("test accuracy", test_accuracy)

    sess = tf.InteractiveSession()
    sess.run(tf.initialize_all_variables())

    ###merge all the summaries and write them out to /tmp/mnist_logs
    merged = tf.merge_all_summaries()
    writer = tf.train.SummaryWriter('./training_logs', sess.graph_def)

    ###strat training and evaluate accuracy per N batches
    for i in range(iterations):
        batch_x, batch_y = cu.get_batch_rand(sentences_train, labels_train, training_batch_size)
        if i % evaluate_per_n_batches == 0:
            ## mini batch accuracy
            result = sess.run([train_accuracy_summary, train_accuracy], feed_dict={x: batch_x, y_: batch_y, keep_prob: 1.0})
            writer.add_summary(result[0], i)
            print 'step %d, training accuracy %g' % (i, result[1])

            ## test accuracy
            if len(sentences_test) > 0:
                result = sess.run([test_accuracy_summary, test_accuracy], feed_dict={x: sentences_test, y_: labels_test, keep_prob: 1.0})
                writer.add_summary(result[0], i)
                print 'step %d, test accuracy %g' % (i, result[1])

        sess.run(train_step, feed_dict={x: batch_x, y_: batch_y, keep_prob: dropout_rate})

    with tf.name_scope('model-output') as scope:
        tf_saver = tf.train.Saver()
        tf_saver.save(sess, model_name)

    if len(sentences_test) > 0:
        test_accuracy_score = test_accuracy.eval(feed_dict={x: sentences_test, y_: labels_test, keep_prob: 1.0})
        print 'test accuracy %g' % test_accuracy_score
        pred, ans = cu.evaluate_pr(tf, x, y_, sentences_test, labels_test, y_conv, keep_prob)

