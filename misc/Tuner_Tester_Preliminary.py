import numpy as np
import pandas as pd
import keras_tuner as kt
import re, os, shutil

from statistics import mean
from tensorflow.keras.preprocessing.text import Tokenizer
from tensorflow.keras.preprocessing.sequence import pad_sequences
from sklearn.model_selection import train_test_split
from sklearn.utils import shuffle

from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Embedding, Conv1D, GlobalMaxPooling1D, Dropout, Dense


def clean_text(text):
    """Cleans an input text (sentence).

    Args:
        text (str): The text to be cleaned.

    Returns:
        string: The cleaned text.
    """

    # remove all non-letters (punctuations, numbers, etc.)
    processed_text = re.sub("[^a-zA-Z]", " ", text)
    # remove single characters
    processed_text = re.sub(r"\s+[a-zA-Z]\s+", " ", processed_text)
    # remove multiple whitespaces
    processed_text = re.sub(r"\s+", " ", processed_text)

    # clean more
    processed_text = re.sub(r"\s+[a-zA-Z]\s+", " ", processed_text)
    processed_text = re.sub(r"\s+", " ", processed_text)
    
    return processed_text


def preprocess(dataframe):
    """Preprocess data which includes cleaning news headlines, mapping string sentiment labels into their integer equivalent,
    and splitting into train and test datasets.

    Args:
        dataframe (pd.Dataframe): Dataframe representing the news headlines and their corresponding sentiment labels.

    Returns:
        np.array (4): Arrays representing the train and test datasets.
    """

    #clean all headlines then lowercase
    clean_headlines = []
    for headline in dataframe["Headline"]:
        clean_headline = clean_text(headline)
        clean_headlines.append(clean_headline.lower())
        
    sentiment_mapping = {
        "negative" : 0,
        "neutral" : 1,
        "positive" : 2
    }

    #convert string sentiment to integer equivalent
    sentiments = []
    for sentiment in dataframe["Sentiment"]:
        sentiments.append(sentiment_mapping[sentiment])
    
    #split dataset to train and test datasets
    train_x, test_x, train_y, test_y = train_test_split(clean_headlines, sentiments, train_size=0.8, shuffle=False)
    
    return np.array(train_x), np.array(test_x), np.array(train_y), np.array(test_y)


def make_tokenizer(train_x):
    """Creates a tokenizer object using the training inputs dataset.

    Args:
        train_x (np.array): Array representing the training inputs dataset.

    Returns:
        keras.Tokenizer: The created tokenizer object.
    """

    #create tokenizer object
    tokenizer = Tokenizer()
    #look at list of texts to count frequency of unique words, most common asigned integer value of 1
    tokenizer.fit_on_texts(train_x)
    
    return tokenizer


def text_to_int(tokenizer, texts, is_train):
    """Converts a set of texts (sentences) into their numerical representations.

    Args:
        tokenizer (keras.Tokenizer): The created tokenizer object.
        texts (list): The list of texts (sentences) to be converted.
        is_train (bool): If set to True, currently converting the training inputs dataset.

    Returns:
        list: A list of lists wherein each element represents the numerical representation of a specific text (sentence).
    """

    #transform sentences into integer representation
    if (is_train):
        sequences = tokenizer.texts_to_sequences(texts)
    else:
        sequences = []
        for text in texts:
            text_list = text.split()
            sequence = []
            for i in range(len(text_list)):
                #tokenizer.word_index is a dictionary with words as keys and integers as values
                if text_list[i] not in tokenizer.word_index:
                    sequence.append(0)
                else:
                    sequence.append(tokenizer.word_index[text_list[i]])

            sequences.append(sequence)
    
    return sequences


def make_cnn_hypermodel(hp, vocab_size, max_seq_length):
    """Builds and returns a CNN hypermodel based on hyperparameters,
    vocab_size, and max_seq_length.

    Args:
        hp (kt hyperparameter): Used by the keras tuner to define the hyperparameters.
        vocab_size (int): The number of words in the vocabulary.
        max_seq_length (int): The length of the longest sequence (sentence).

    Returns:
        kt hypermodel: A model created and tested by keras tuner.
    """

    #a hypermodel has keras tuner hyperparameters (hp) that are variable
    cnn_hypermodel = Sequential()

    #set hyperparameters to be searched in Hyperband tuning
    filters = hp.Choice('filters', values=[32, 64, 128, 256])
    kernel_size = hp.Choice('kernel_size', values=[3, 4, 5, 6])
    rate = hp.Float('rate', min_value=0.0, max_value=0.9, step=0.1)
    
    #create CNN hypermodel
    cnn_hypermodel.add(Embedding(input_dim=vocab_size, output_dim=300, input_length=max_seq_length))
    cnn_hypermodel.add(Conv1D(filters=filters, kernel_size=kernel_size, activation="relu"))
    cnn_hypermodel.add(GlobalMaxPooling1D())
    cnn_hypermodel.add(Dropout(rate=rate))
    cnn_hypermodel.add(Dense(3, activation="softmax"))

    cnn_hypermodel.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])

    return cnn_hypermodel


def get_optimal_hps(train_x, train_y, vocab_size, max_seq_length):
    """Returns optimal direction forecasting model hyperparameters.

    Args:
        train_x (np.array): Array representing the training inputs dataset.
        train_y (np.array): Array representing the training targets dataset.
        vocab_size (int): The number of words in the vocabulary.
        max_seq_length (int): The length of the longest sequence (sentence).

    Returns:
        dict: A dictionary representing the optimal hyperparameters gotten using keras tuner
        utilizing the Hyperband optimization algorithm.
    """

    #the tuner saves files to the current working directory, delete old files if any
    if os.path.exists('untitled_project'):
        shutil.rmtree('untitled_project')

    hypermodel_builder = lambda hp : make_cnn_hypermodel(hp, vocab_size, max_seq_length)
    print("Now tuning")

    #if overwrite is false, previously-saved computed hps will be used
    tuner = kt.Hyperband(hypermodel_builder, objective='val_loss', max_epochs=50, factor=3, overwrite=True)

    #execute Hyperband search of optimal hyperparameters
    early_stopping_callback = EarlyStopping(monitor='val_loss', patience=3, mode='min')
    tuner.search(train_x, train_y, validation_split=0.25, callbacks=[early_stopping_callback])
    
    #hps is a dictionary of optimal hyperparameter levels
    hps = (tuner.get_best_hyperparameters(num_trials=1)[0]).values.copy()

    #delete files saved by tuner in current working directory
    shutil.rmtree('untitled_project')
    
    return hps


def make_cnn_model(hps, vocab_size, max_seq_length):
    """Builds and compiles a CNN model.

    Args:
        hps (dict): A dictionary representing model hyperparameters.
        vocab_size (int): The number of words in the vocabulary.
        max_seq_length (int): The length of the longest sequence (sentence).

    Returns:
        keras.model: The CNN model built and compiled.
    """

    model = Sequential()

    filters = hps["filters"]
    kernel_size = hps["kernel_size"]
    rate = hps["rate"]
    
    model.add(Embedding(input_dim=vocab_size, output_dim=300, input_length=max_seq_length))
    model.add(Conv1D(filters=filters, kernel_size=kernel_size, activation="relu"))
    model.add(GlobalMaxPooling1D())
    model.add(Dropout(rate=rate))
    model.add(Dense(3, activation="softmax"))

    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])

    return model


def train_cnn_model(model, train_x, train_y):
    """Trains the CNN model based on the given training dateset.

    Args:
        model (keras.model): The CNN model built and compiled.
        train_x (np.array): Array representing the training inputs dataset.
        train_y (np.array): Array representing the training targets dataset.

    Returns:
        model (keras.model): The trained CNN model.
    """

    early_stopping_callback = EarlyStopping(monitor='val_loss', patience=3, mode='min')
    model.fit(train_x, train_y, epochs=50, verbose=0, validation_split=0.25, callbacks=[early_stopping_callback])

    print("Training Done")
    
    return model


def get_accuracy(model, test_x, test_y):
    """Evaluates the trained CNN model on the test dataset.

    Args:
        model (keras.model): The trained CNN model.
        test_x (np.array): Array representing the test inputs dataset.
        test_y (np.array): Array representing the test targets dataset.

    Returns:
        float: The accuracy of the trained CNN model.
    """

    score = model.evaluate(test_x, test_y, verbose=0)
    
    return round(score[1], 6)


def experiment(hps):
    """Function that creates and evaluates a single CNN model.

    Args:
        hps (dict): A dictionary representing model hyperparameters.

    Returns:
        model, keras.model: The created CNN model.
        accuracy, float: The accuracy of the created CNN model.
        tokenizer, keras.Tokenizaer: The tokenizer object created based on the training inputs dataset.
        max_seq_length, int: The length of the longest sequence (sentence).
    """

    # shuffle and split data
    data = pd.read_csv("all-data.csv", names=["Sentiment", "Headline"], encoding="latin-1")
    data = shuffle(data)
    train_x, test_x, train_y, test_y = preprocess(data)

    # create tokenizer object
    tokenizer = make_tokenizer(train_x)

    # create vocabulary
    vocab = tokenizer.word_index
    vocab_size = len(vocab) + 1
    
    # convert sentences into numerical sequences
    train_sequences = text_to_int(tokenizer, train_x, True)
    test_sequences = text_to_int(tokenizer, test_x, False)
    
    # pad sequences up to the length of the longest sequence
    max_seq_length = max(np.max(list(map(lambda x: len(x), train_sequences))), np.max(list(map(lambda x: len(x), test_sequences))))
    train_x = pad_sequences(train_sequences, maxlen=max_seq_length, padding="post")
    test_x = pad_sequences(test_sequences, maxlen=max_seq_length, padding="post")

    # comment out if tuning
    #hps = get_optimal_hps(train_x, train_y, vocab_size, max_seq_length)

    # build, compile, and train the CNN model
    model = train_cnn_model(make_cnn_model(hps, vocab_size, max_seq_length), train_x, train_y)
    
    return model, get_accuracy(model, test_x, test_y), tokenizer, max_seq_length


def main():
    # choice of hps
    hps_default = {"filters": 128, "kernel_size": 3, "rate": 0.5}
    hps_tuned = {"filters": 128, "kernel_size": 4, "rate": 0.2}
    hps = hps_tuned

    # set repeats to 1 if tuning and comment out line 296
    repeats = 5
    accuracies = []
    for i in range(repeats):
        print(f"Model {i + 1} / {repeats}")
        curr_model, curr_accuracy, curr_tokenizer, max_seq_length = experiment(hps)
        accuracies.append(curr_accuracy)
        if (i == 0):
            best_model = curr_model
            best_accuracy = curr_accuracy
            tokenizer = curr_tokenizer
        elif (curr_accuracy > best_accuracy):
            best_model = curr_model
            best_accuracy = curr_accuracy
            tokenizer = curr_tokenizer

    print()
    print("HPs:", hps)        
    print("Accuracies: " + str(accuracies))
    print("Mean accuracy: " + str(mean(accuracies)))
    print("Best accuracy: " + str(best_accuracy))
    
    # testing arbitrary texts
    samples = ["AboitizPower starts clean energy farm", "PLDT posts record revenues, exceeds profit target in 2021", "PH shares down as Ukraine tensions persist | Inquirer Business"]
    
    clean_samples = []
    for sample in samples:
        clean_sample = clean_text(sample)
        clean_samples.append(clean_sample.lower())
        
    sequences = text_to_int(tokenizer, clean_samples, False)
    sequences = pad_sequences(sequences, maxlen=max_seq_length, padding="post")
    sequences = np.array(sequences)
    
    print()
    count = 0
    for sequence in sequences:
        prediction = best_model.predict(sequence.reshape(1, max_seq_length))
        score = prediction[0][-1] - prediction[0][0]

        print("Sample text:", samples[count])
        print("Prediction:", prediction)
        print("Final score:", score)

        count += 1

if __name__ == '__main__':
    main()