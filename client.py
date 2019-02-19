# import required libraries
import sys, re
from socket import *
import threading
import os
from urllib.parse import urlparse
import time, pickle

lock_1 = threading.Lock()
flag =1

def progress(metric_interval, thread_no):
	j = 0
	cnt = 0
	total_1 = 0
	total_2 = sum([total for chunk,total in thread_no])

	# display downloading progress after specified metric_interval
	while(1):
		lock_1.acquire()
		cnt +=1
		for i in thread_no: # for each thread
			if(j>len(thread_no)-1): #bcuz for loop runs one too many times
				break
			
			# display metrics for each connection after metric_interval
			if(thread_no[j][1]==0):
				print("Connection ", j, ": ", thread_no[j][0], "/", thread_no[j][1], ", download speed: 0 kb/s")
			else:
				print("Connection ", j, ": ", thread_no[j][0], "/", thread_no[j][1], ", download speed: ", (thread_no[j][0]/1000)/(metric_interval*cnt), "kb/s")
			total_1 += thread_no[j][0]
			j+=1

		# display metrics for total bytes
		print("Total : ", total_1, "/", total_2, ", download speed: ", (total_1/1000)/(metric_interval*cnt), "kb/s")
		total_1 = 0
		j=0
		print()
		time.sleep(metric_interval)

		# After all threads have finished execution
		if (flag == 0):
			cnt+=1
			for i in thread_no: # for each thread
				if(j>len(thread_no)-1): #bcuz for loop runs one too many times
					break
				
				# display metrics for each connection after metric_interval
				if(thread_no[j][1]==0):
					print("Connection ", j, ": ", thread_no[j][0], "/", thread_no[j][1], ", download speed: 0 kb/s")
				else:
					print("Connection ", j, ": ", thread_no[j][0], "/", thread_no[j][1], ", download speed: ", (thread_no[j][0]/1000)/(metric_interval*cnt), "kb/s")
				total_1 += thread_no[j][0]
				j+=1
			
			# display metrics for total bytes
			print("Total : ", total_1, "/", total_2, ", download speed: ", (total_1/1000)/(metric_interval*cnt), "kb/s")
			print()
			break
		lock_1.release()

def download(start_byte, end_byte, thread_num,thread_no, soc):
	# display each thread downloading range
	print("Thread ",thread_num,": range = ", start_byte, " to ",end_byte)

	# send get request to server for data of a defined range
	sockets_list[thread_num].send(bytes("GET " + file_location + " HTTP/1.1\r\nHost: " + host +
	 "\r\nRange: bytes=" + str(start_byte) + "-" + str(end_byte) +"\r\n\r\n",'utf-8'))
	
	# open seperate file within the directory for every thread to write the data
	with open(os.path.join(output_location.split(".")[0], str(thread_num) + ".txt"),'ab') as output_file:
		header = True
		while True:
			# get response from the server
			response = sockets_list[thread_num].recv(1024)
			# loop termination condition
			if not response:
				break
			# if header is in the response remove header and get content data only
			if header:
				partition_data = response.decode("ASCII").split("\r\n\r\n")[1]
				header = False
			# if content only then simply get the content
			else:
				partition_data = response.decode("ASCII")
			
			# update the download status of chunk
			thread_no[thread_num][0]+=len(partition_data)
			# write downloaded bytes to file
			output_file.write(bytes(partition_data,'utf-8'))
			# write the download status of chunk to csv.txt
			with open(os.path.join(output_location.split(".")[0],"csv.txt"),'wb') as csv_file:
				pickle.dump(thread_no, csv_file)
				csv_file.close()
		
def tcp_connection(thread_no):
	byte_range = []

	# if not resuming 
	if resume == False:
		# create tcp socket
		soc = socket(AF_INET, SOCK_STREAM)
		# connect socket to host
		soc.connect((host, port))
		# get the header of the file
		soc.send(bytes("HEAD " + file_location + " HTTP/1.1\r\nHost: " + host + "\r\n\r\n",'utf-8'))

		# get the total content length of the file
		response = soc.recv(1024).decode("ASCII")
		content_length = int(re.findall("Content-Length: (.*?)\r\n",response, re.DOTALL)[-1])
		# calculate offset of every chunk
		offset = content_length // num_connections

		# calculate start_byte and end_byte of every chunk
		start_byte = 0
		end_byte = offset
		for n in range(num_connections-1):
			byte_range.append([start_byte,end_byte])
			start_byte = end_byte + 1
			end_byte += offset
		byte_range.append([start_byte,content_length])

		# initialize the download status list
		for n in range(num_connections):
			ran = byte_range[n][1] - byte_range[n][0] + 1
			thread_no.append([0, ran])

		# dump the download status in csv.txt for later use in resuming
		with open(os.path.join(output_location.split(".")[0],"csv.txt"),'wb') as csv_file:
			pickle.dump(thread_no, csv_file)
			csv_file.close()

	# if resume downloading
	else:
		# get download status from csv.txt
		with open(os.path.join(output_location.split(".")[0],"csv.txt"),'rb') as csv_file:
			thread_no = pickle.load(csv_file)
			csv_file.close()

		# calculate start_byte and end_byte of every chunk from download status
		start_byte = thread_no[0][0] + 1
		end_byte = thread_no[0][1]
		byte_range.append([start_byte, end_byte])
		for n in range(1, num_connections):
			start_byte = end_byte + thread_no[n][0] + 1
			end_byte += thread_no[n][1]
			byte_range.append([start_byte, end_byte])

	# create n tcp sockets
	for n in range(num_connections):
		sock = socket(AF_INET, SOCK_STREAM)
		sock.connect((host,port))
		sockets_list.append(sock)

	# starting the metric interval thread
	t = threading.Timer(metric_interval, progress,[metric_interval,thread_no])
	t.start() 

	# starting all threads to download data chunks from start_byte to end_byte
	for n in range(num_connections):
		t = threading.Thread(target=download, args=(byte_range[n][0],byte_range[n][1],n,thread_no,sockets_list,))
		t.start()
		threads.append(t)

	# synchronizing all threads
	for t in threads:
		t.join()

	global flag
	flag = 0

	# combining all chunks data to a large final.txt file
	with open(os.path.join(output_location.split(".")[0],"final.txt"),'wb') as final_file:
		for thread_num in range(num_connections):
			with open(os.path.join(output_location.split(".")[0], str(thread_num) + ".txt"),'rb') as output_file:
				final_file.write(output_file.read())
	print(thread_no)
	print("Download Successful!")

if __name__ == '__main__':
	# client.py -r -n <num_connections> -i <metric_interval> -c <connection_type> -f <file_location> -o <output_location> 
	argc = len(sys.argv)

	# check for correct no of arguments given
	if argc < 11:
		print("Usage: " + sys.argv[0] + " -r -n <num_connections> -i <metric_interval> -c <connection_type> -f <file_location> -o <output_location>")
		exit()

	# check for resuming
	if sys.argv[1] == "-r":
		resume = True
	else:
		resume = False

	# assigning command line arguments to variables
	output_location = sys.argv[argc-1]
	file_location = sys.argv[argc-3]
	connection_type = sys.argv[argc-5]
	metric_interval = float(sys.argv[argc-7])
	num_connections = int(sys.argv[argc-9])

	sockets_list = []
	threads = []
	thread_no = []
	port = 80

	# check if url was given
	if re.search("www",file_location) is not None:
		host = urlparse(file_location).netloc
		file_location = urlparse(file_location).path
	else:
		host = "localhost"

	# create destination directory if not exists
	if not os.path.exists(output_location.split(".")[0]):
		os.mkdir(output_location.split(".")[0])
	
	# check for connection type
	if connection_type == "TCP":
		tcp_connection(thread_no)
	elif connection_type == "UDP":
		print("Try TCP!")