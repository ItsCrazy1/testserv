CREATE TABLE SUBSCRIBERS(
	ID smallserial PRIMARY KEY,
	VK_USER_ID int NOT NULL,
	SB_TESTSERVER_RELEASES boolean DEFAULT false NOT NULL,
	TIMESTAMP timestamp DEFAULT current_timestamp
)