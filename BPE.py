# https://arxiv.org/abs/1508.07909 Byte-Pair Encoding (BPE)
# https://lovit.github.io/nlp/2018/04/02/wpm/ 참고

import re, collections
import numpy as np # 1.15
import csv
import time
import os
from tqdm import tqdm



def save_data(path, data):
	np.save(path, data)

def load_data(path, mode=None):
	data = np.load(path, encoding='bytes')
	if mode == 'dictionary':
		data = data.item()
	return data


# word:"abc" => "a b c space_symbol"
def word_split_for_bpe(word, space_symbol='</w>'):
	return ' '.join(list(word)) + ' ' + space_symbol


# word frequency 추출.
def get_word_frequency_dict_from_document(path, space_symbol='</w>'):
	word_frequency_dict = {}

	with open(path, 'r', encoding='utf-8') as f:
		for i, sentence in enumerate(f):
			# EOF check
			if sentence == '\n' or sentence == ' ' or sentence == '':
				break

			if sentence[-1] == '\n':
				sentence = sentence[:-1]

			for word in sentence.split():					
				# "abc" => "a b c space_symbol"
				word = word_split_for_bpe(word, space_symbol)
							
				# word frequency
				if word in word_frequency_dict:
					word_frequency_dict[word] += 1
				else:
					word_frequency_dict[word] = 1

	return word_frequency_dict



# merge two dictionary
def merge_dictionary(dic_a, dic_b):
	for i in dic_b:
		if i in dic_a:
			dic_a[i] += dic_b[i]
		else:
			dic_a[i] = dic_b[i]
	return dic_a


# 2-gram frequency table 추출.
def get_stats(word_frequency_list):
	pairs = {}
	for word, freq in word_frequency_list:
		symbols = word.split()
		for i in range(len(symbols)-1):
			gram = (symbols[i],symbols[i+1])
			if gram in pairs:
				pairs[gram] += freq
			else:
				pairs[gram] = freq
	return pairs # tuple을 담고 있는 dictionary 리턴.



# pairs 중에서 가장 높은 frequency를 갖는 key 리턴.
def check_merge_info(pairs):
	best = max(pairs, key=pairs.get)
	return best



# frequency가 가장 높은 best_pair 정보를 이용해서 단어를 merge.
def merge_bpe_word(best_pair_and_word_frequency_list):
	best_pair = best_pair_and_word_frequency_list[0] # tuple ('r','</w>')
	word_frequency = best_pair_and_word_frequency_list[1] # list

	v_out = []

	bigram = re.escape(' '.join(best_pair))
	p = re.compile(r'(?<!\S)' + bigram + r'(?!\S)')
	for word, freq in word_frequency:
		# 만약 ''.join(best_pair): r</w> 이고, word: 'a r </w>' 이면 w_out은 'a r</w>'가 된다.
		w_out = p.sub(''.join(best_pair), word)
		v_out.append( (w_out, freq) )

	if len(best_pair_and_word_frequency_list) == 3: # multi proc
		return (best_pair_and_word_frequency_list[2], v_out) # (multiproc 결과 조합할 순서, 결과)
	else:
		return v_out



def merge_a_word(merge_info, word, cache={}):
	# merge_info: list
	# word: "c e m e n t </w>" => "ce m e n t<\w>" 되어야 함.
	
	#if len(word.split()) == 1:
	if word.count(' ') == 0:
		return word

	if word in cache:
		return cache[word]
	else:
		bpe_word = word
		for info in merge_info:
			if bpe_word.count(' ') == 0:
				break

			bigram = re.escape(' '.join(info))
			p = re.compile(r'(?<!\S)' + bigram + r'(?!\S)')

			# 만약 ''.join(info): r</w> 이고, bpe_word: 'a r </w>' 이면 w_out은 'a r</w>'가 된다.
			bpe_word = p.sub(''.join(info), bpe_word)

		# cache upate
		cache[word] = bpe_word
		return bpe_word


def make_bpe2idx(word_frequency_list, npy_path):
	word_frequency_dict = {}
	for word, freq in word_frequency_list:
		# ex: ('B e it r a g</w>', 8)
		split = word.split() # [B e it r a g</w>]
		for bpe in split:
			if bpe not in word_frequency_dict:
				word_frequency_dict[bpe] = freq
			else:
				word_frequency_dict[bpe] += freq

	sorted_voca = sorted(tuple(word_frequency_dict.items()), key=lambda x: x[1], reverse=True)

	bpe2idx = {
			'</p>':0,
			'UNK':1,
			'</g>':2, #go
			'</e>':3 #eos
		}	
	idx2bpe = {
			0:'</p>',
			1:'UNK',
			2:'</g>', #go
			3:'</e>' #eos
		}
	idx = 4

	with open(npy_path+'sorted_voca.txt', 'w', encoding='utf-8') as o:
		for voca, freq in sorted_voca:
			o.write(str(voca) + ' ' + str(freq) + '\n')
			bpe2idx[voca] = idx
			idx2bpe[idx] = voca
			idx += 1

	return bpe2idx, idx2bpe



# 문서를 읽고, bpe 적용. cache 사용할것. apply_bpe에서 사용.
def _apply_bpe(path, out_path, space_symbol='</w>', merge_info=None, cache={}):
	start = time.time()

	cache_len = len(cache)

	# write file
	o = open(out_path, 'w', newline='', encoding='utf-8')
	wr = csv.writer(o, delimiter=' ')

	with open(path, 'r', encoding='utf-8') as f:
		for i, sentence in enumerate(f):
			row = []
			if sentence == '\n' or sentence == ' ' or sentence == '':
				break
			
			if sentence[-1] == '\n':
				sentence = sentence[:-1]			

			before_cache_len = len(cache)
			for word in sentence.split():
				# "abc" => "a b c space_symbol"
				split_word = word_split_for_bpe(word, space_symbol)
				
				# merge_info를 이용해서 merge.  "a b c </w>" ==> "ab c</w>"
				merge = merge_a_word(merge_info, split_word, cache)
				
				# 안합쳐진 부분은 다른 단어로 인식해서 공백기준 split 처리해서 sentence에 extend
				row.extend(merge.split())
			wr.writerow(row)

			if (i+1) % 100000 == 0:
				current_cache_len = len(cache)
				print('out_path:', out_path, 'line:', i+1, 'total cache:', current_cache_len, 'added:', current_cache_len-cache_len)
				cache_len = current_cache_len

	o.close()


def _learn_bpe(word_frequency_dict, npy_path, num_merges=37000, multi_proc=1):
	#word_frequency_dict = {'l o w </w>' : 1, 'l o w e r </w>' : 1, 'n e w e s t </w>':1, 'w i d e s t </w>':1}
	
	merge_info = [] # 합친 정보를 기억하고있다가 다른 데이터에 적용.
	word_frequency = list(word_frequency_dict.items())
	del word_frequency_dict
	cache_list = word_frequency.copy() # 나중에 word -> bpe 처리 할 때, 빠르게 하기 위함.

	# init multiprocessing
	if multi_proc > 1:
		import multiprocessing as mp

		process = multi_proc  #os.cpu_count()
		print('# process:', process)

		slice_size =  len(word_frequency)//process
		slicing = [k*slice_size for k in range(process)]
		slicing.append(len(word_frequency)) # [0, @@, ..., len(word_frequency_dict)] # 총 process+1개 
		print(slicing)
		pool = mp.Pool(process)

	for i in tqdm(range(num_merges), ncols=50):
		# 2gram별 빈도수 추출
		if multi_proc > 1:		
			get_stats_results = pool.map(
					get_stats, 
					[word_frequency[slicing[k]:slicing[k+1]] for k in range(process)]
				)
			# merge
			pairs={}
			for dic in get_stats_results:
				pairs = merge_dictionary(pairs, dic)
		else:
			pairs = get_stats(word_frequency) 
		#######

		# 가장 높은 빈도의 2gram 선정
		best = check_merge_info(pairs) # 가장 높은 빈도의 2gram 선정
		merge_info.append(best) #merge 하는데 사용된 정보 저장.
		#######
		
		# 가장 높은 빈도의 2gram으로 merge
		if multi_proc > 1:		
			merge_results = pool.map(
					merge_bpe_word, 
					zip( [best]*process, [word_frequency[slicing[k]:slicing[k+1]] for k in range(process)], [k for k in range(process)] )
				)
			# merge
			merge_results = dict(merge_results)
			
			word_frequency = []		
			for order in range(process):
				word_frequency.extend(merge_results[order])
		else:
			word_frequency = merge_bpe_word((best, word_frequency)) # 가장 높은 빈도의 2gram을 합침.
		######

	# multiproc close
	if multi_proc > 1:		
		pool.close()


	# make npy
	if not os.path.exists(npy_path):
		print("create" + npy_path + "directory")
		os.makedirs(npy_path)

	# 빠른 변환을 위한 cache 저장. 기존 word를 key로, bpe 결과를 value로.	
	cache = {}
	for i in range(len(cache_list)): 
		key = cache_list[i][0]
		value = word_frequency[i][0]
		cache[key] = value

	save_data(npy_path+'merge_info.npy', merge_info) # list
	save_data(npy_path+'cache.npy', cache) # dict
	print('save merge_info.npy', ', size:', len(merge_info))
	print('save cache.npy', ', size:', len(cache))

	
	bpe2idx, idx2bpe = make_bpe2idx(word_frequency, npy_path)
	save_data(npy_path+'bpe2idx.npy', bpe2idx) # dict
	save_data(npy_path+'idx2bpe.npy', idx2bpe) # dict
	print('save bpe2idx.npy', ', size:', len(bpe2idx))
	print('save idx2bpe.npy', ', size:', len(idx2bpe))	

	

def learn_bpe(path_list, npy_path, space_symbol='</w>', num_merges=37000, voca_threshold=5, multi_proc=1):
	
	print('get word frequency dictionary')
	total_word_frequency_dict = {}
	for path in path_list:
		word_frequency_dict = get_word_frequency_dict_from_document(
				path=path, 
				space_symbol=space_symbol, 
			) #ok
		total_word_frequency_dict = merge_dictionary(total_word_frequency_dict, word_frequency_dict)


	# 빈도수가 일정 미만인 단어 제외.	
	total_word_frequency_dict_size = len(total_word_frequency_dict)
	for item in list(total_word_frequency_dict.items()):
		if item[1] < voca_threshold: # item[0] is key, item[1] is value
			del total_word_frequency_dict[item[0]]
	print('frequency word dict size:', total_word_frequency_dict_size)
	print('threshold applied frequency word dict size:', len(total_word_frequency_dict), 'removed:', total_word_frequency_dict_size-len(total_word_frequency_dict), '\n')


	print('learn bpe')
	_learn_bpe(
			total_word_frequency_dict, 
			npy_path=npy_path,
			num_merges=num_merges,
			multi_proc=multi_proc
		)

	print('\n\n\n')



def apply_bpe(path_list, out_bpe_path, out_list, npy_path, space_symbol='</w>', pad_symbol='</p>'):
	if not os.path.exists(out_bpe_path):
		print("create" + out_bpe_path + "directory")
		os.makedirs(out_bpe_path)

	merge_info = load_data(npy_path+'merge_info.npy')
	cache = load_data(npy_path+'cache.npy', mode='dictionary')
	
	print('apply bpe')
	for i in range(len(path_list)):
		path = path_list[i]
		out_path = out_list[i]

		print('path:', path, ', out_path:', out_path)
		_apply_bpe(
				path=path, 
				out_path=out_bpe_path+out_path,
				space_symbol=space_symbol, 
				merge_info=merge_info, 
				cache=cache
			)
		save_data(npy_path+'cache.npy', cache)
	print('\n\n\n')



# save directory
npy_path = './npy/' # path of bpe2idx, idx2bpe, merge_info and cache 
out_bpe_path = './bpe_dataset/' # bpe applied path

# train data path
path_list = ["./dataset/corpus.tc.en/corpus.tc.en", "./dataset/corpus.tc.de/corpus.tc.de"] # original data1, data2
out_list = ['./bpe_wmt17.en', './bpe_wmt17.de'] # bpe_applied_data1, data2


# test data path
test_path_list = [
		'./dataset/dev.tar/newstest2014.tc.en',
		'./dataset/dev.tar/newstest2015.tc.en',
		'./dataset/dev.tar/newstest2016.tc.en',
	]
test_out_list = [
		'./bpe_newstest2014.en', 
		'./bpe_newstest2015.en', 
		'./bpe_newstest2016.en', 
	] 		

# learn and apply
if __name__ == '__main__':
	# if don't use multiprocessing:
	# learn_bpe(path_list, npy_path, space_symbol='</w>', top_k=None)
	# multi_proc: # process,  os.cpu_count(): # cpu processor of current computer
	
	# learn bpe from documents
	learn_bpe(path_list, npy_path, space_symbol='</w>', num_merges=35000, voca_threshold=50, multi_proc=os.cpu_count())
	#learn_bpe(path_list, npy_path, space_symbol='</w>', num_merges=30000, voca_threshold=5, multi_proc=os.cpu_count())

	# apply bpe to documents
	apply_bpe(path_list, out_bpe_path, out_list, npy_path, space_symbol='</w>', pad_symbol='</p>')
	apply_bpe(test_path_list, out_bpe_path, test_out_list, npy_path, space_symbol='</w>', pad_symbol='</p>')


