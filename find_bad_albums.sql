SELECT a2.name, s.title, s.file  
FROM album a 
INNER JOIN song s ON a.id=s.album 
INNER JOIN artist a2 ON s.artist=a2.id 
WHERE a.NAME != '[non-album tracks]' AND a.mbid IS NULL;
